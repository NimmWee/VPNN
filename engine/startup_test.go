package engine

import (
	"net"
	"testing"
	"time"
)

func TestDNSStartupHasDeadlineAndStopsOwnedRuntime(t *testing.T) {
	blackhole, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer blackhole.Close()
	var m Manager
	m.startupTimeout = 150 * time.Millisecond
	cfg := Config{Mode: "dns", Listen: unusedTCP(t), DNS: &DNSConfig{
		Domains: []string{"v.example.test"}, Resolvers: []string{blackhole.LocalAddr().String()},
		Key: "0123456789abcdef0123456789abcdef", Encryption: 5,
	}}
	if err := m.Start(cfg, t.TempDir(), nil, nil); err != nil {
		t.Fatal(err)
	}
	defer m.Stop()
	for deadline := time.Now().Add(3 * time.Second); time.Now().Before(deadline); time.Sleep(10 * time.Millisecond) {
		if m.Status().State == "error" {
			if m.Status().Error == "" {
				t.Fatal("startup failure has no diagnostic")
			}
			if err := m.Stop(); err != nil {
				t.Fatal(err)
			}
			if m.Status().State != "idle" {
				t.Fatal("stop did not clear the failed runtime")
			}
			return
		}
	}
	t.Fatal("DNS stayed connecting after its startup deadline")
}
