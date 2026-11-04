//go:build windows

package core

import (
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"testing"
	"time"

	"golang.org/x/net/proxy"
	"vpnn.local/engine"
)

func TestVpnnWindowsProtectedDNSHTTPS(t *testing.T) {
	path := os.Getenv("VPNN_DNS_TEST_CONFIG")
	if path == "" {
		t.Skip("set VPNN_DNS_TEST_CONFIG for explicit SOCKS diagnostics without TUN or host routes")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal("cannot read private test configuration")
	}
	var cfg engine.Config
	if json.Unmarshal(data, &cfg) != nil || cfg.Mode != "dns" {
		t.Fatal("expected a DNS engine configuration")
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	cfg.Listen = listener.Addr().String()
	listener.Close()
	previousBind := vpnnRequiresBind.Swap(false)
	t.Cleanup(func() { vpnnRequiresBind.Store(previousBind) })
	var manager engine.Manager
	if err := manager.Start(cfg, t.TempDir(), vpnnProtectFD, nil); err != nil {
		t.Fatal("protected DNS startup failed")
	}
	defer manager.Stop()
	for deadline := time.Now().Add(60 * time.Second); manager.Status().State != "ready"; time.Sleep(100 * time.Millisecond) {
		if manager.Status().State == "error" || time.Now().After(deadline) {
			t.Fatal("protected DNS did not become ready")
		}
	}
	dialer, err := proxy.SOCKS5("tcp", cfg.Listen, nil, &net.Dialer{Timeout: 10 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	transport := &http.Transport{DialContext: dialer.(proxy.ContextDialer).DialContext}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 30 * time.Second}
	response, err := client.Get("https://api.ipify.org/")
	if err != nil {
		t.Fatal("HTTPS through protected DNS transport failed")
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 128))
	if err != nil || response.StatusCode != 200 || net.ParseIP(string(body)) == nil {
		t.Fatal("invalid HTTPS egress response")
	}
	t.Logf("HTTPS through Windows-protected DNS succeeded; egress=%s", body)
}
