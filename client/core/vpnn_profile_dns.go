package core

import (
	"errors"
	"net"
	"net/url"
	"strconv"
	"strings"

	"github.com/metacubex/mihomo/config"
	"go.yaml.in/yaml/v3"
)

func pinVpnnDNS(raw *config.RawConfig) error {
	transport, err := vpnnConfigFromProxies(raw.Proxy)
	if err != nil || transport == nil {
		return err
	}
	var servers []string
	if transport.Mode == "dns" {
		_, port, _ := net.SplitHostPort(transport.Listen)
		n, _ := strconv.Atoi(port)
		servers = []string{"udp://127.0.0.1:" + strconv.Itoa(n+1)}
	} else {
		var name string
		for _, proxy := range raw.Proxy {
			if _, ok := proxy["x-vpnn"]; ok {
				name, _ = proxy["name"].(string)
			}
		}
		if name == "" || strings.ContainsAny(name, "&#=") {
			return errors.New("embedded proxy requires a DNS-safe name")
		}
		for _, host := range []string{"1.1.1.1", "8.8.8.8"} {
			u := url.URL{Scheme: "https", Host: host, Path: "/dns-query", Fragment: name}
			servers = append(servers, u.String())
		}
	}
	// Overlay DNS settings must not create a direct path around the selected transport.
	raw.DNS.Enable = true
	raw.DNS.RespectRules = false
	raw.DNS.PreferH3 = false
	raw.DNS.NameServer = servers
	raw.DNS.DefaultNameserver = servers
	raw.DNS.ProxyServerNameserver = servers
	raw.DNS.DirectNameServer = servers
	raw.DNS.Fallback = nil
	raw.DNS.NameServerPolicy = nil
	raw.DNS.ProxyServerNameserverPolicy = nil
	return nil
}

func pinVpnnDocumentDNS(root *yaml.Node) error {
	raw := config.DefaultRawConfig()
	if err := root.Decode(raw); err != nil {
		return err
	}
	if transport, err := vpnnConfigFromProxies(raw.Proxy); err != nil || transport == nil {
		return err
	}
	if err := pinVpnnDNS(raw); err != nil {
		return err
	}
	var dns yaml.Node
	if err := dns.Encode(raw.DNS); err != nil {
		return err
	}
	setMappingValue(root, "dns", &dns)
	return nil
}
