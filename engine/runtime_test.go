package engine

import (
	"context"
	"encoding/hex"
	"encoding/json"
	free "github.com/samosvalishe/free-turn-proxy/mobile"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func unusedTCP(t *testing.T) string {
	t.Helper()
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	a := l.Addr().String()
	l.Close()
	return a
}

func TestInvalidNewConfigDoesNotStopOwnedRuntime(t *testing.T) {
	var m Manager
	stops := 0
	m.stop = func() error { stops++; return nil }
	if err := m.Start(Config{Mode: "bad"}, t.TempDir(), nil, nil); err == nil {
		t.Fatal("invalid config accepted")
	}
	if stops != 0 {
		t.Fatal("invalid config destroyed the current session")
	}
	if err := m.Stop(); err != nil {
		t.Fatal(err)
	}
	if err := m.Stop(); err != nil {
		t.Fatal(err)
	}
	if stops != 1 || m.Status().State != "idle" {
		t.Fatal("stop was not idempotent")
	}
}

func TestFreeTurnEmbeddedTCPRoundTripAndStop(t *testing.T) {
	server := os.Getenv("VPNN_FREETURN_SERVER")
	if server == "" {
		t.Skip("set VPNN_FREETURN_SERVER to a source-built server for local protocol integration")
	}
	backend, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer backend.Close()
	go func() {
		for {
			c, err := backend.Accept()
			if err != nil {
				return
			}
			go func() { defer c.Close(); io.Copy(c, c) }()
		}
	}()
	udp, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	peer := udp.LocalAddr().String()
	udp.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	key := hex.EncodeToString(make([]byte, 32))
	cmd := exec.CommandContext(ctx, server, "-listen", peer, "-connect", backend.Addr().String(), "-mode", "tcp", "-obf-profile", "rtpopus3", "-obf-key", key)
	log, err := os.Create(filepath.Join(t.TempDir(), "server.log"))
	if err != nil {
		t.Fatal(err)
	}
	defer log.Close()
	defer func() {
		if t.Failed() {
			log.Sync()
			data, _ := os.ReadFile(log.Name())
			t.Logf("server: %s\nclient: %s", data, free.DumpLogs())
		}
	}()
	cmd.Stdout = log
	cmd.Stderr = log
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { cancel(); cmd.Wait() }()
	listen := unusedTCP(t)
	raw, _ := json.Marshal(map[string]any{"provider": "direct", "peer": peer, "clientId": "vpnn-local-test", "proxy": map[string]any{"mode": "tcp"}, "turn": map[string]any{"n": 1}, "obf": map[string]any{"profile": "rtpopus3", "key": key}})
	var m Manager
	if err := m.Start(Config{Mode: "vk", Listen: listen, VK: raw}, t.TempDir(), nil, nil); err != nil {
		t.Fatal(err)
	}
	defer m.Stop()
	for deadline := time.Now().Add(15 * time.Second); time.Now().Before(deadline) && m.Status().State != "connected"; time.Sleep(100 * time.Millisecond) {
	}
	if m.Status().State != "connected" {
		t.Fatalf("transport did not become ready: %+v", m.Status())
	}
	var conn net.Conn
	for deadline := time.Now().Add(15 * time.Second); time.Now().Before(deadline); time.Sleep(100 * time.Millisecond) {
		conn, err = net.DialTimeout("tcp", listen, 100*time.Millisecond)
		if err == nil {
			break
		}
	}
	if err != nil {
		t.Fatalf("embedded relay listener: %v", err)
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(10 * time.Second))
	message := []byte("VPNN embedded FreeTurn local round trip")
	if _, err := conn.Write(message); err != nil {
		t.Fatal(err)
	}
	got := make([]byte, len(message))
	if _, err := io.ReadFull(conn, got); err != nil {
		t.Fatal(err)
	}
	if string(got) != string(message) {
		t.Fatal("forwarded bytes changed")
	}
	conn.Close()
	if err := m.Stop(); err != nil {
		t.Fatal(err)
	}
	if c, err := net.DialTimeout("tcp", listen, 200*time.Millisecond); err == nil {
		c.Close()
		t.Fatal("transport listener remained open after disconnect")
	}
}
