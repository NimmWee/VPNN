package core

import (
	"encoding/json"
	"testing"
	"time"
	"vpnn.local/engine"

	"github.com/metacubex/mihomo/config"
)

func TestVpnnMetadataSurvivesProfileMerge(t *testing.T) {
	path := writeBaseProfile(t, `proxies:
  - name: VPNN
    type: socks5
    server: 127.0.0.1
    port: 19082
    x-vpnn:
      mode: dns
      listen: 127.0.0.1:19082
      dns: {domains: [v.example.test], resolvers: ["127.0.0.1:5300"], key: 0123456789abcdef0123456789abcdef}
proxy-groups: [{name: VPNN mode, type: select, proxies: [VPNN]}]
rules: ["MATCH,VPNN mode"]
`)
	base, err := handleGetProfileBase(path)
	if err != nil {
		t.Fatal(err)
	}
	doc, err := mergeProfileBase(&SetupBase{Path: path, Overlay: overlayOf(t, base, nil, nil)})
	if err != nil {
		t.Fatal(err)
	}
	raw := config.DefaultRawConfig()
	if err := doc.Decode(raw); err != nil {
		t.Fatal(err)
	}
	c, err := vpnnConfigFromProxies(raw.Proxy)
	if err != nil {
		t.Fatal(err)
	}
	if c == nil || c.Mode != "dns" || c.Listen != "127.0.0.1:19082" {
		t.Fatal("metadata was lost or changed")
	}
	if len(raw.DNS.NameServer) != 1 || raw.DNS.NameServer[0] != "udp://127.0.0.1:19083" {
		t.Fatal("profile merge did not pin site DNS to the embedded tunnel")
	}
}

func TestVpnnCachedAccessExpiryAndFailedStart(t *testing.T) {
	deadline, err := vpnnAccessDeadline([]map[string]any{{"x-vpnn-valid-until": time.Now().Add(-time.Hour).Unix()}})
	if err != nil {
		t.Fatal(err)
	}
	if validateVpnnDeadline(deadline) == nil {
		t.Fatal("expired managed profile accepted")
	}
	oldConfig, oldRunning, oldTransport := currentConfig, isRunning.Load(), vpnnConfigured
	defer func() { currentConfig = oldConfig; isRunning.Store(oldRunning); vpnnConfigured = oldTransport }()
	currentConfig = nil
	vpnnConfigured = &engine.Config{Mode: "bad", Listen: "127.0.0.1:19082"}
	if handleStartListener() || isRunning.Load() {
		t.Fatal("failed embedded transport reported a running connection")
	}
}

func TestVpnnSystemResolversAreDeduplicatedAndDoNotLoopToLocalDNS(t *testing.T) {
	got := vpnnDNSResolvers([]string{"1.1.1.1:53", "127.0.0.1:5300"}, []string{"10.0.2.3", "1.1.1.1", "127.0.0.1", "not-an-ip", "::1"})
	if len(got) != 3 || got[0] != "10.0.2.3:53" || got[1] != "1.1.1.1:53" || got[2] != "127.0.0.1:5300" {
		t.Fatalf("unexpected resolver candidates: %v", got)
	}
}

func TestVpnnRejectsMismatchedEndpointAndOverlappingTransports(t *testing.T) {
	var proxy map[string]any
	json.Unmarshal([]byte(`{"name":"VPNN","type":"socks5","server":"8.8.8.8","port":19082,"x-vpnn":{"mode":"dns","listen":"127.0.0.1:19082","dns":{"domains":["v.example.test"],"resolvers":["127.0.0.1:5300"],"key":"0123456789abcdef0123456789abcdef"}}}`), &proxy)
	if _, err := vpnnConfigFromProxies([]map[string]any{proxy}); err == nil {
		t.Fatal("public endpoint accepted for a local transport")
	}
	proxy["server"] = "127.0.0.1"
	if _, err := vpnnConfigFromProxies([]map[string]any{proxy, proxy}); err == nil {
		t.Fatal("two embedded transports accepted")
	}
}
