package wbstream

import (
	"bytes"
	"context"
	"errors"
	"net"
	"net/url"
	"os"
	"strconv"
	"testing"
	"time"

	"github.com/livekit/protocol/auth"
	"github.com/livekit/protocol/livekit"
	"github.com/livekit/protocol/logger"
	lksdk "github.com/livekit/server-sdk-go/v2"
	"github.com/pion/stun/v3"
)

func TestLiveKit(t *testing.T) {
	endpoint := os.Getenv("WB_LAB_URL")
	if endpoint == "" {
		t.Skip("run lab.ps1 to start the isolated LiveKit server")
	}
	lksdk.SetLogger(logger.GetDiscardLogger())
	u, err := url.Parse(endpoint)
	if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" {
		t.Fatal("the test requires a loopback HTTP endpoint")
	}
	port, err := strconv.Atoi(u.Port())
	if err != nil || port < 1024 || port > 65532 {
		t.Fatal("invalid lab port")
	}
	startSTUN(t, port+3)
	key, secret := os.Getenv("WB_LAB_KEY"), os.Getenv("WB_LAB_SECRET")
	room := "wb-p6-" + time.Now().UTC().Format("20060102T150405.000000000")
	token := func(identity, signingSecret string) string {
		t.Helper()
		jwt, err := auth.NewAccessToken(key, signingSecret).
			SetIdentity(identity).SetValidFor(time.Minute).
			SetVideoGrant(&auth.VideoGrant{RoomJoin: true, Room: room}).ToJWT()
		if err != nil {
			t.Fatal(err)
		}
		return jwt
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	config := func(me, peer, signingSecret string) Config {
		return Config{URL: endpoint, Token: token(me, signingSecret), Room: room, Identity: me, PeerIdentity: peer}
	}
	if session, err := Open(ctx, config("creator", "joiner", "wrong-signing-secret-xxxxxxxxxxxx")); err == nil {
		session.Close()
		t.Fatal("accepted invalid signature")
	}
	t.Log("PASS invalid JWT rejected")
	creator, err := Open(ctx, config("creator", "joiner", secret))
	if err != nil {
		t.Fatal(err)
	}
	defer creator.Close()
	joinCtx, stopJoiner := context.WithCancel(ctx)
	defer stopJoiner()
	joiner, err := Open(joinCtx, config("joiner", "creator", secret))
	if err != nil {
		t.Fatal(err)
	}
	defer joiner.Close()
	for _, s := range []*Session{creator, joiner} {
		if err := s.WaitReady(ctx); err != nil {
			t.Fatal(err)
		}
	}
	t.Log("PASS VP8 RTP received in both directions through SFU")
	for _, pair := range [][2]*Session{{creator, joiner}, {joiner, creator}} {
		for i := range 32 {
			want := bytes.Repeat([]byte{0, byte(i), 255, 128}, 256)
			if err := pair[0].Send(want); err != nil {
				t.Fatal(err)
			}
			got, err := pair[1].Receive(ctx)
			if err != nil || !bytes.Equal(got, want) {
				t.Fatalf("packet %d: got %d bytes, want %d, err=%v", i, len(got), len(want), err)
			}
		}
	}
	t.Log("PASS 32 KiB per direction over reliable DataChannel")
	if err := creator.Send(make([]byte, MaxPayload+1)); !errors.Is(err, ErrPayload) {
		t.Fatalf("oversized payload: %v", err)
	}

	api := lksdk.NewRoomServiceClient(endpoint, key, secret)
	if _, err := api.RemoveParticipant(ctx, &livekit.RoomParticipantIdentity{Room: room, Identity: "creator"}); err != nil {
		t.Fatal(err)
	}
	for _, s := range []*Session{creator, joiner} {
		select {
		case <-s.Done():
		case <-ctx.Done():
			t.Fatal("SFU eviction did not close session")
		}
		if !errors.Is(s.Err(), ErrDisconnected) {
			t.Fatalf("SFU eviction: %v", s.Err())
		}
	}
	t.Log("PASS SFU eviction closes both ends")

	reopened, err := Open(joinCtx, config("joiner", "creator", secret))
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	stopJoiner()
	select {
	case <-reopened.Done():
	case <-ctx.Done():
		t.Fatal("cancel did not close session")
	}
	reopened.Close()
	reopened.Close()
	if err := reopened.Send([]byte("closed")); !errors.Is(err, context.Canceled) {
		t.Fatalf("send after close: %v", err)
	}
	if _, err := reopened.Receive(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("receive after close: %v", err)
	}
	stopped, err := Open(ctx, config("creator", "joiner", secret))
	if err != nil {
		t.Fatal(err)
	}
	stopped.Close()
	if err := stopped.Err(); !errors.Is(err, ErrClosed) {
		t.Fatalf("explicit close: %v", err)
	}
	for {
		list, err := api.ListParticipants(ctx, &livekit.ListParticipantsRequest{Room: room})
		if err != nil {
			t.Fatal(err)
		}
		if len(list.Participants) == 0 {
			break
		}
		select {
		case <-ctx.Done():
			t.Fatal("participants remain after cleanup")
		case <-time.After(50 * time.Millisecond):
		}
	}
	t.Log("PASS context cancellation, explicit and repeat Close, zero participants")
}

// Return the actual loopback source as a reflexive ICE candidate.
func startSTUN(t *testing.T, port int) {
	t.Helper()
	socket, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: port})
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan struct{})
	t.Cleanup(func() {
		socket.Close()
		<-done
	})
	go func() {
		defer close(done)
		buf := make([]byte, 1500)
		for {
			n, source, err := socket.ReadFromUDP(buf)
			if err != nil {
				return
			}
			var req stun.Message
			if err := stun.Decode(buf[:n], &req); err != nil || req.Type != stun.BindingRequest {
				continue
			}
			reply, err := stun.Build(&req, stun.BindingSuccess,
				&stun.XORMappedAddress{IP: source.IP, Port: source.Port}, stun.Fingerprint)
			if err == nil {
				_, _ = socket.WriteToUDP(reply.Raw, source)
			}
		}
	}()
}
