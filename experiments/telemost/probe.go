// Package telemost contains a loopback-only WebRTC transport probe.
package telemost

import (
	"context"
	"errors"
	"fmt"
	"net"

	"github.com/pion/webrtc/v4"
)

// MaxPayload bounds the probe to one binary message in each direction.
const MaxPayload = 16 << 10

// Probe sends payload over a local reliable DataChannel and returns its echo.
// The call owns both peers and releases them before returning.
func Probe(ctx context.Context, payload []byte) ([]byte, error) {
	if len(payload) == 0 || len(payload) > MaxPayload {
		return nil, fmt.Errorf("payload must contain 1 to %d bytes", MaxPayload)
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	left, err := listenLoopback()
	if err != nil {
		return nil, err
	}
	right, err := listenLoopback()
	if err != nil {
		_ = left.Close()
		return nil, err
	}
	return exchange(ctx, left, right, payload, func(message []byte) []byte { return message })
}

func listenLoopback() (*net.UDPConn, error) {
	return net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
}

func localPeer(socket *net.UDPConn) (*webrtc.PeerConnection, func(), error) {
	mux := webrtc.NewICEUDPMux(nil, socket)
	settings := webrtc.SettingEngine{}
	settings.SetNetworkTypes([]webrtc.NetworkType{webrtc.NetworkTypeUDP4})
	settings.SetIncludeLoopbackCandidate(true)
	settings.SetIPFilter(func(ip net.IP) bool { return ip.IsLoopback() })
	settings.SetICEUDPMux(mux)
	pc, err := webrtc.NewAPI(webrtc.WithSettingEngine(settings)).NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		_ = mux.Close()
		return nil, nil, err
	}
	return pc, func() {
		_ = pc.GracefulClose()
		_ = mux.Close()
	}, nil
}

// exchange takes ownership of both sockets, including on early failure.
func exchange(ctx context.Context, left, right *net.UDPConn, payload []byte, reply func([]byte) []byte) ([]byte, error) {
	defer left.Close()
	defer right.Close()
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	sender, closeSender, err := localPeer(left)
	if err != nil {
		return nil, err
	}
	defer closeSender()
	receiver, closeReceiver, err := localPeer(right)
	if err != nil {
		return nil, err
	}
	defer closeReceiver()

	failures := make(chan error, 1)
	report := func(err error) {
		select {
		case failures <- err:
		default:
		}
	}
	receiver.OnDataChannel(func(dc *webrtc.DataChannel) {
		dc.OnError(report)
		dc.OnMessage(func(msg webrtc.DataChannelMessage) {
			if answer := reply(msg.Data); answer != nil {
				if err := dc.Send(answer); err != nil {
					report(err)
				}
			}
		})
	})
	dc, err := sender.CreateDataChannel("telemost-local-probe", nil)
	if err != nil {
		return nil, err
	}
	result := make(chan []byte, 1)
	dc.OnError(report)
	dc.OnClose(func() { report(errors.New("data channel closed")) })
	dc.OnMessage(func(msg webrtc.DataChannelMessage) {
		select {
		case result <- msg.Data:
		default:
		}
	})
	dc.OnOpen(func() {
		if ctx.Err() == nil {
			if err := dc.Send(payload); err != nil {
				report(err)
			}
		}
	})
	if err := negotiate(ctx, sender, receiver); err != nil {
		return nil, fmt.Errorf("loopback signaling: %w", err)
	}
	select {
	case data := <-result:
		return data, ctx.Err()
	case err := <-failures:
		return nil, err
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func negotiate(ctx context.Context, offerer, answerer *webrtc.PeerConnection) error {
	offer, err := offerer.CreateOffer(nil)
	if err != nil {
		return err
	}
	if err := gather(ctx, offerer, offer); err != nil {
		return err
	}
	if err := answerer.SetRemoteDescription(*offerer.LocalDescription()); err != nil {
		return err
	}
	answer, err := answerer.CreateAnswer(nil)
	if err != nil {
		return err
	}
	if err := gather(ctx, answerer, answer); err != nil {
		return err
	}
	return offerer.SetRemoteDescription(*answerer.LocalDescription())
}

func gather(ctx context.Context, pc *webrtc.PeerConnection, desc webrtc.SessionDescription) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	complete := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(desc); err != nil {
		return err
	}
	select {
	case <-complete:
	case <-ctx.Done():
	}
	return ctx.Err()
}
