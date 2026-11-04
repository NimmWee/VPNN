package wbstream

import (
	"bytes"
	"context"
	"encoding/hex"
	"errors"
	"net/url"
	"sync"
	"time"

	"github.com/livekit/protocol/livekit"
	"github.com/livekit/protocol/logger"
	lksdk "github.com/livekit/server-sdk-go/v2"
	"github.com/pion/rtp/codecs"
	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
)

const (
	MaxPayload    = 1024
	topic         = "vpnn.wb-p6.v1"
	trackName     = "vpnn-wb-p6-vp8"
	frameInterval = 100 * time.Millisecond
)

var (
	ErrDisconnected = errors.New("livekit session disconnected")
	ErrClosed       = errors.New("livekit session closed")
	ErrNotReady     = errors.New("remote VP8 track is not ready")
	ErrPayload      = errors.New("payload must be between 1 and 1024 bytes")
	ErrOverflow     = errors.New("receive queue full")
	// One synthetic 16x16 black VP8 keyframe, without its IVF header.
	probeFrame, _ = hex.DecodeString("1002009d012a100010000047088585888584880202000c0d6000feffab5080")
)

// Config contains the already authorized LiveKit session. Token is secret.
type Config struct {
	URL, Token, Room, Identity, PeerIdentity string
}

type Session struct {
	ctx      context.Context
	stop     context.CancelCauseFunc
	room     *lksdk.Room
	peer     string
	incoming chan []byte
	ready    chan struct{}
	done     chan struct{}
	mu       sync.Mutex
	closing  bool
	readers  sync.WaitGroup
}

// Open connects and publishes a synthetic camera track. ctx owns the session.
func Open(ctx context.Context, cfg Config) (*Session, error) {
	u, err := url.Parse(cfg.URL)
	if err != nil || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" ||
		(u.Scheme != "wss" && !(u.Scheme == "http" && u.Hostname() == "127.0.0.1")) {
		return nil, errors.New("expected a WSS SFU endpoint or local lab HTTP endpoint")
	}
	if cfg.Token == "" || cfg.Room == "" || cfg.Identity == "" || cfg.PeerIdentity == "" || cfg.Identity == cfg.PeerIdentity {
		return nil, errors.New("token, room and distinct participant identities required")
	}
	lifetime, stop := context.WithCancelCause(ctx)
	s := &Session{
		ctx: lifetime, stop: stop, peer: cfg.PeerIdentity,
		incoming: make(chan []byte, 32), ready: make(chan struct{}), done: make(chan struct{}),
	}
	var readyOnce sync.Once
	cb := lksdk.NewRoomCallback()
	cb.OnDisconnected = func() { stop(ErrDisconnected) }
	cb.OnReconnecting = func() { stop(ErrDisconnected) }
	cb.OnParticipantDisconnected = func(peer *lksdk.RemoteParticipant) {
		if peer.Identity() == s.peer {
			stop(ErrDisconnected)
		}
	}
	cb.OnDataPacket = func(packet lksdk.DataPacket, params lksdk.DataReceiveParams) {
		data, ok := packet.(*lksdk.UserDataPacket)
		if !ok || params.SenderIdentity != s.peer || data.Topic != topic ||
			len(data.Payload) == 0 || len(data.Payload) > MaxPayload || lifetime.Err() != nil {
			return
		}
		select {
		case s.incoming <- bytes.Clone(data.Payload):
		default:
			stop(ErrOverflow)
		}
	}
	cb.OnTrackSubscribed = func(track *webrtc.TrackRemote, pub *lksdk.RemoteTrackPublication, peer *lksdk.RemoteParticipant) {
		if peer.Identity() != s.peer || pub.Name() != trackName || track.Codec().MimeType != webrtc.MimeTypeVP8 {
			return
		}
		s.mu.Lock()
		if s.closing {
			s.mu.Unlock()
			return
		}
		s.readers.Add(1)
		s.mu.Unlock()
		go func() {
			defer s.readers.Done()
			for lifetime.Err() == nil {
				if err := track.SetReadDeadline(time.Now().Add(time.Second)); err != nil {
					return
				}
				packet, _, err := track.ReadRTP()
				if err != nil {
					return
				}
				var vp8 codecs.VP8Packet
				payload, err := vp8.Unmarshal(packet.Payload)
				if err == nil && vp8.S == 1 && packet.Marker && bytes.Equal(payload, probeFrame) {
					readyOnce.Do(func() { close(s.ready) })
				}
			}
		}()
	}
	s.room = lksdk.NewRoom(cb)
	track, err := lksdk.NewLocalTrack(webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeVP8, ClockRate: 90000})
	if err != nil {
		stop(err)
		return nil, err
	}
	joinCtx, cancel := context.WithTimeout(lifetime, 8*time.Second)
	defer cancel()
	opts := &lksdk.TrackPublicationOptions{
		Name: trackName, Source: livekit.TrackSource_CAMERA, VideoWidth: 16, VideoHeight: 16,
	}
	cleanup := func() {
		s.mu.Lock()
		s.closing = true
		s.mu.Unlock()
		_ = track.Close()
		s.room.Disconnect()
		s.readers.Wait()
		close(s.done)
	}
	if err := s.room.JoinWithContextAndToken(joinCtx, cfg.URL, cfg.Token, lksdk.WithLogger(logger.GetDiscardLogger())); err != nil {
		cause := context.Cause(joinCtx)
		stop(ErrDisconnected)
		cleanup()
		if cause != nil {
			return nil, cause
		}
		return nil, errors.New("LiveKit join rejected")
	}
	if s.room.Name() != cfg.Room || s.room.LocalParticipant.Identity() != cfg.Identity {
		err := errors.New("LiveKit room or local identity mismatch")
		stop(err)
		cleanup()
		return nil, err
	}
	if _, err := s.room.LocalParticipant.PublishTrack(track, opts); err != nil {
		cause := context.Cause(lifetime)
		stop(ErrDisconnected)
		cleanup()
		if cause != nil {
			return nil, cause
		}
		return nil, errors.New("LiveKit VP8 publication rejected")
	}
	if err := s.Err(); err != nil {
		cleanup()
		return nil, err
	}
	go func() {
		defer cleanup()
		ticker := time.NewTicker(frameInterval)
		defer ticker.Stop()
		for {
			select {
			case <-lifetime.Done():
				return
			case <-ticker.C:
				if err := track.WriteSample(media.Sample{Data: probeFrame, Duration: frameInterval}, nil); err != nil {
					stop(ErrDisconnected)
					return
				}
			}
		}
	}()
	return s, nil
}

// WaitReady observes the expected VP8 probe. It does not prove data or egress.
func (s *Session) WaitReady(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-s.ctx.Done():
		return s.Err()
	case <-s.ready:
		return s.Err()
	}
}

func (s *Session) Send(payload []byte) error {
	if err := s.Err(); err != nil {
		return err
	}
	if len(payload) == 0 || len(payload) > MaxPayload {
		return ErrPayload
	}
	select {
	case <-s.ready:
	default:
		return ErrNotReady
	}
	return s.room.LocalParticipant.PublishDataPacket(&lksdk.UserDataPacket{Topic: topic, Payload: payload},
		lksdk.WithDataPublishReliable(true), lksdk.WithDataPublishDestination([]string{s.peer}))
}

func (s *Session) Receive(ctx context.Context) ([]byte, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-s.ctx.Done():
		return nil, s.Err()
	case packet := <-s.incoming:
		if err := s.Err(); err != nil {
			return nil, err
		}
		return packet, nil
	}
}

// Done closes after the local track, room and receive workers are closed.
func (s *Session) Done() <-chan struct{} { return s.done }
func (s *Session) Err() error            { return context.Cause(s.ctx) }

func (s *Session) Close() {
	s.stop(ErrClosed)
	<-s.done
}
