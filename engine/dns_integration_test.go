package engine

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"golang.org/x/net/proxy"
)

func TestMasterDNSEmbeddedHTTPSAndResolver(t *testing.T) {
	server := os.Getenv("VPNN_MASTERDNS_SERVER")
	if server == "" {
		t.Skip("set VPNN_MASTERDNS_SERVER to a source-built server for encrypted DNS integration")
	}
	dir := t.TempDir()
	key := "0123456789abcdef0123456789abcdef"
	keyFile := filepath.Join(dir, "encrypt_key.txt")
	if err := os.WriteFile(keyFile, []byte(key), 0600); err != nil {
		t.Fatal(err)
	}
	udp, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	resolver := udp.LocalAddr().String()
	_, port, _ := net.SplitHostPort(resolver)
	n, _ := strconv.Atoi(port)
	udp.Close()
	data, _ := json.Marshal(map[string]any{"UDP_HOST": "127.0.0.1", "UDP_PORT": n, "DOMAIN": []string{"v.example.test"}, "PROTOCOL_TYPE": "SOCKS5", "DATA_ENCRYPTION_METHOD": 5, "ENCRYPTION_KEY_FILE": keyFile, "LOG_LEVEL": "ERROR"})
	configFile := filepath.Join(dir, "server.json")
	if err := os.WriteFile(configFile, data, 0600); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, server, "-config", configFile)
	log, err := os.Create(filepath.Join(dir, "server.log"))
	if err != nil {
		t.Fatal(err)
	}
	defer log.Close()
	cmd.Stdout = log
	cmd.Stderr = log
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { cancel(); cmd.Wait() }()
	defer func() {
		if t.Failed() {
			log.Sync()
			b, _ := os.ReadFile(log.Name())
			t.Logf("server: %s", b)
		}
	}()
	listen := unusedTCP(t)
	_, localPort, _ := net.SplitHostPort(listen)
	localN, _ := strconv.Atoi(localPort)
	if localN == 65535 {
		t.Skip("ephemeral port has no next UDP port")
	}
	var calls atomic.Int64
	var m Manager
	if err := m.Start(Config{Mode: "dns", Listen: listen, DNS: &DNSConfig{Domains: []string{"v.example.test"}, Resolvers: []string{resolver}, Key: key, Encryption: 5}}, dir, func(int) bool { calls.Add(1); return true }, nil); err != nil {
		t.Fatal(err)
	}
	defer m.Stop()
	for deadline := time.Now().Add(60 * time.Second); time.Now().Before(deadline) && m.Status().State != "ready"; time.Sleep(100 * time.Millisecond) {
	}
	if m.Status().State != "ready" {
		t.Fatalf("DNS transport did not become ready: %+v", m.Status())
	}
	dialer, err := proxy.SOCKS5("tcp", listen, nil, &net.Dialer{Timeout: 10 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	transport := &http.Transport{DialContext: dialer.(proxy.ContextDialer).DialContext}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 20 * time.Second}
	response, err := client.Get("https://example.com/")
	if err != nil {
		t.Fatal(err)
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, 64000))
	response.Body.Close()
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != 200 || !strings.Contains(string(body), "Example Domain") {
		t.Fatalf("unexpected HTTPS response %d", response.StatusCode)
	}
	dnsResolver := &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "udp", net.JoinHostPort("127.0.0.1", strconv.Itoa(localN+1)))
	}}
	lookupCtx, lookupCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer lookupCancel()
	addresses, err := dnsResolver.LookupHost(lookupCtx, "example.com")
	if err != nil || len(addresses) == 0 {
		t.Fatalf("tunneled DNS lookup: %v", err)
	}
	if calls.Load() == 0 {
		t.Fatal("upstream protection callback never ran")
	}
	if err := m.Stop(); err != nil {
		t.Fatal(err)
	}
	if c, err := net.DialTimeout("tcp", listen, 200*time.Millisecond); err == nil {
		c.Close()
		t.Fatal("SOCKS listener remained open after stop")
	}
}
