package telemost

import (
	"bytes"
	"context"
	"errors"
	"net"
	"testing"
	"time"
)

func TestDataChannelRoundTripAndCleanup(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	left, right := testSockets(t)
	want := make([]byte, 16<<10)
	for i := range want {
		want[i] = byte(i ^ (i >> 8))
	}
	got, err := exchange(ctx, left, right, want, func(message []byte) []byte { return message })
	if err != nil || !bytes.Equal(got, want) {
		t.Fatalf("round trip: got %d bytes, error %v", len(got), err)
	}
	t.Logf("DC: %d bytes verified byte for byte", len(got))
	assertReleased(t, left, right)
}

func TestCancelWhileWaitingForReply(t *testing.T) {
	deadline, stop := context.WithTimeout(context.Background(), 10*time.Second)
	defer stop()
	ctx, cancel := context.WithCancel(deadline)
	defer cancel()
	left, right := testSockets(t)
	received := make(chan struct{}, 1)
	done := make(chan error, 1)
	go func() {
		_, err := exchange(ctx, left, right, []byte("cancel after delivery"), func([]byte) []byte {
			received <- struct{}{}
			return nil
		})
		done <- err
	}()
	select {
	case <-received:
	case err := <-done:
		t.Fatalf("exchange ended before delivery: %v", err)
	case <-deadline.Done():
		t.Fatal("request was not delivered")
	}
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("got %v, want context.Canceled", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("cancellation did not stop the exchange")
	}
	assertReleased(t, left, right)
}

func TestCanceledBeforeSignaling(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	left, right := testSockets(t)
	_, err := exchange(ctx, left, right, []byte("unused"), func(message []byte) []byte { return message })
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("got %v, want context.Canceled", err)
	}
	assertReleased(t, left, right)
}

func testSockets(t *testing.T) (*net.UDPConn, *net.UDPConn) {
	t.Helper()
	open := func() *net.UDPConn {
		conn, err := listenLoopback()
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(func() { _ = conn.Close() })
		return conn
	}
	return open(), open()
}

func assertReleased(t *testing.T, sockets ...*net.UDPConn) {
	t.Helper()
	for _, socket := range sockets {
		addr := socket.LocalAddr().(*net.UDPAddr)
		if err := socket.SetReadDeadline(time.Now()); !errors.Is(err, net.ErrClosed) {
			t.Fatalf("socket %s still open: %v", addr, err)
		}
		rebound, err := net.ListenUDP("udp4", addr)
		if err != nil {
			t.Fatalf("cannot rebind %s: %v", addr, err)
		}
		_ = rebound.Close()
		t.Logf("UDP socket closed and port rebound: %s", addr)
	}
}

func TestProbe(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	want := []byte{0, 0xff, 0x10}
	got, err := Probe(ctx, want)
	if err != nil || !bytes.Equal(got, want) {
		t.Fatalf("Probe returned %x, %v", got, err)
	}
}
