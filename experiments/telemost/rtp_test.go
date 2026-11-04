package telemost

import (
	"bytes"
	"context"
	"testing"
	"time"

	"github.com/pion/rtp"
	"github.com/pion/webrtc/v4"
)

// This checks RTP carriage on a negotiated VP8 track. It does not decode VP8.
func TestLocalVP8RTP(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	left, right := testSockets(t)
	send, closeSend, err := localPeer(left)
	if err != nil {
		t.Fatal(err)
	}
	defer closeSend()
	recv, closeRecv, err := localPeer(right)
	if err != nil {
		t.Fatal(err)
	}
	defer closeRecv()

	track, err := webrtc.NewTrackLocalStaticRTP(
		webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeVP8, ClockRate: 90000}, "probe", "local",
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := send.AddTrack(track); err != nil {
		t.Fatal(err)
	}
	if _, err := recv.AddTransceiverFromKind(webrtc.RTPCodecTypeVideo,
		webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly}); err != nil {
		t.Fatal(err)
	}

	type received struct {
		codec string
		pkt   *rtp.Packet
		err   error
	}
	result := make(chan received, 1)
	recv.OnTrack(func(remote *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		pkt, _, err := remote.ReadRTP()
		select {
		case result <- received{remote.Codec().MimeType, pkt, err}:
		case <-ctx.Done():
		}
	})
	if err := negotiate(ctx, send, recv); err != nil {
		t.Fatal(err)
	}

	payload := append([]byte{0x10}, []byte("local RTP probe")...) // VP8 descriptor, then opaque test bytes.
	pkt := rtp.Packet{Header: rtp.Header{Version: 2, Marker: true}, Payload: payload}
	ticker := time.NewTicker(20 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case got := <-result:
			if got.err != nil {
				t.Fatal(got.err)
			}
			if got.codec != webrtc.MimeTypeVP8 || !got.pkt.Marker || !bytes.Equal(got.pkt.Payload, payload) {
				t.Fatalf("unexpected RTP packet on %s: %+v", got.codec, got.pkt)
			}
			t.Logf("RTP: negotiated %s, verified %d payload bytes", got.codec, len(payload))
			return
		case <-ticker.C:
			pkt.SequenceNumber++
			pkt.Timestamp += 1800
			if err := track.WriteRTP(&pkt); err != nil {
				t.Fatal(err)
			}
		case <-ctx.Done():
			t.Fatal(ctx.Err())
		}
	}
}
