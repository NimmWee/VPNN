package core

import (
	"net"
	"net/netip"
	"sync/atomic"

	"github.com/metacubex/mihomo/component/resolver"
)

var vpnnAndroidDNS atomic.Pointer[[]string]

func setVpnnSystemDNS(servers []string) {
	copy := append([]string(nil), servers...)
	vpnnAndroidDNS.Store(&copy)
}

func vpnnDNSResolvers(configured, system []string) []string {
	result := []string{}
	seen := map[string]bool{}
	add := func(address string) {
		if len(result) < 16 && !seen[address] {
			seen[address] = true
			result = append(result, address)
		}
	}
	for _, value := range system {
		address, err := netip.ParseAddr(value)
		if err != nil || address.IsLoopback() || address.IsUnspecified() || address.IsMulticast() || resolver.IsSystemDnsBlacklisted(value) {
			continue
		}
		add(net.JoinHostPort(address.String(), "53"))
	}
	for _, value := range configured {
		add(value)
	}
	return result
}

func handleVpnnNetworkChange() bool {
	configMu.Lock()
	defer configMu.Unlock()
	if !isRunning.Load() || vpnnConfigured == nil {
		return true
	}
	if err := vpnnRuntime.Stop(); err != nil {
		return false
	}
	if err := startConfiguredVpnn(); err != nil {
		logError("embedded transport network reset failed: %v", err)
		return false
	}
	return true
}
