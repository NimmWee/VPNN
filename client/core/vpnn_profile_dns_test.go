package core

import (
	"reflect"
	"testing"

	"github.com/metacubex/mihomo/config"
)

func TestVpnnDNSOverridesCannotEscapeEmbeddedTransport(t *testing.T) {
	for _, mode := range []string{"dns", "vk"} {
		t.Run(mode, func(t *testing.T) {
			meta := map[string]any{"mode": mode, "listen": "127.0.0.1:19082"}
			if mode == "dns" {
				meta["dns"] = map[string]any{"domains": []string{"v.example.test"}, "resolvers": []string{"1.1.1.1:53"}, "key": "0123456789abcdef0123456789abcdef"}
			} else {
				meta["vk"] = map[string]any{"peer": "192.0.2.1:56010", "clientId": "test"}
			}
			raw := config.DefaultRawConfig()
			raw.Proxy = []map[string]any{{"name": "VPNN", "type": "socks5", "server": "127.0.0.1", "port": 19082, "x-vpnn": meta}}
			raw.DNS.Enable = false
			raw.DNS.RespectRules = true
			raw.DNS.Fallback = []string{"8.8.8.8"}
			raw.DNS.DirectNameServer = []string{"8.8.4.4"}
			if err := pinVpnnDNS(raw); err != nil {
				t.Fatal(err)
			}
			want := []string{"udp://127.0.0.1:19083"}
			if mode == "vk" {
				want = []string{"https://1.1.1.1/dns-query#VPNN", "https://8.8.8.8/dns-query#VPNN"}
			}
			if !raw.DNS.Enable || raw.DNS.RespectRules || !reflect.DeepEqual(raw.DNS.NameServer, want) || len(raw.DNS.Fallback) != 0 || !reflect.DeepEqual(raw.DNS.DirectNameServer, want) || !reflect.DeepEqual(raw.DNS.DefaultNameserver, want) || !reflect.DeepEqual(raw.DNS.ProxyServerNameserver, want) || raw.DNS.NameServerPolicy != nil || raw.DNS.ProxyServerNameserverPolicy != nil {
				t.Fatalf("DNS escaped owned transport: %+v", raw.DNS)
			}
			if _, err := config.ParseRawConfig(raw); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestVpnnDoesNotChangeOrdinaryProfileDNS(t *testing.T) {
	raw := config.DefaultRawConfig()
	want := raw.DNS
	if err := pinVpnnDNS(raw); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(want, raw.DNS) {
		t.Fatal("ordinary DNS changed")
	}
}
