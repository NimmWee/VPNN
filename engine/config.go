package engine

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/netip"
	"strconv"
	"strings"
)

type Config struct {
	Mode   string          `json:"mode" yaml:"mode"`
	Listen string          `json:"listen" yaml:"listen"`
	VK     json.RawMessage `json:"vk,omitempty" yaml:"vk,omitempty"`
	DNS    *DNSConfig      `json:"dns,omitempty" yaml:"dns,omitempty"`
}

type DNSConfig struct {
	Domains         []string `json:"domains"`
	Resolvers       []string `json:"resolvers"`
	Key             string   `json:"key"`
	Encryption      int      `json:"encryption,omitempty"`
	SystemResolvers bool     `json:"systemResolvers,omitempty"`
}

func (c Config) Validate() error {
	host, port, err := net.SplitHostPort(c.Listen)
	n, parseErr := strconv.Atoi(port)
	if err != nil || parseErr != nil || host != "127.0.0.1" || n < 1024 || n > 65535 {
		return errors.New("transport listener must be 127.0.0.1 on a port from 1024 to 65535")
	}
	switch c.Mode {
	case "vk":
		_, err := c.VKJSON()
		return err
	case "dns":
		if n == 65535 {
			return errors.New("DNS reserves the next UDP port for tunneled DNS queries")
		}
		if c.DNS == nil || len(c.DNS.Domains) == 0 || len(c.DNS.Domains) > 8 || len(c.DNS.Resolvers) == 0 || len(c.DNS.Resolvers) > 16 || len(c.DNS.Key) < 16 {
			return errors.New("DNS requires domains, IP resolvers and an encryption key of at least 16 characters")
		}
		if c.DNS.Encryption != 0 && (c.DNS.Encryption < 3 || c.DNS.Encryption > 5) {
			return errors.New("DNS requires AES-GCM encryption (3, 4 or 5)")
		}
		keyLength := 32
		if c.DNS.Encryption == 3 {
			keyLength = 16
		} else if c.DNS.Encryption == 4 {
			keyLength = 24
		}
		if len(c.DNS.Key) != keyLength {
			return fmt.Errorf("DNS encryption method requires exactly %d key characters", keyLength)
		}
		for _, d := range c.DNS.Domains {
			if len(d) > 190 || !validDomain(d) {
				return errors.New("invalid tunnel domain")
			}
		}
		for _, r := range c.DNS.Resolvers {
			ap, err := netip.ParseAddrPort(r)
			if err != nil || ap.Port() == 0 || ap.Addr().IsUnspecified() || ap.Addr().IsMulticast() {
				return errors.New("resolver must be an IP:port")
			}
		}
		return nil
	default:
		return errors.New("unknown transport mode")
	}
}

func validDomain(d string) bool {
	if !strings.Contains(d, ".") {
		return false
	}
	for _, label := range strings.Split(strings.TrimSuffix(d, "."), ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, r := range label {
			if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '-') {
				return false
			}
		}
	}
	return true
}

func (c Config) VKJSON() ([]byte, error) {
	var v map[string]any
	if err := json.Unmarshal(c.VK, &v); err != nil || v == nil {
		return nil, errors.New("VK configuration must be a JSON object")
	}
	if v["peer"] == nil || v["clientId"] == nil {
		return nil, errors.New("VK requires peer and an individual clientId")
	}
	vk, _ := v["vk"].(map[string]any)
	if vk == nil {
		vk = map[string]any{}
	}
	vk["manualCaptcha"], vk["autoCaptcha"], vk["advancedCaptcha"] = true, false, false
	v["vk"] = vk
	v["routes"], v["subUrl"] = false, ""
	v["tunnel"] = map[string]any{"mode": "none"}
	proxy, _ := v["proxy"].(map[string]any)
	if proxy == nil {
		proxy = map[string]any{"mode": "udp"}
	}
	proxy["listen"] = c.Listen
	v["proxy"] = proxy
	turn, _ := v["turn"].(map[string]any)
	if turn == nil {
		turn = map[string]any{"n": 6}
	}
	if n, ok := turn["n"].(float64); ok && (n < 1 || n > 12) {
		return nil, fmt.Errorf("TURN streams must be between 1 and 12")
	}
	v["turn"] = turn
	if proxy["mode"] == "tcp" {
		if _, explicit := proxy["bond"]; !explicit {
			if n, ok := turn["n"].(float64); !ok || n >= 2 {
				proxy["bond"] = true
			}
		}
	}
	v["log"] = map[string]any{"debug": false}
	return json.Marshal(v)
}
