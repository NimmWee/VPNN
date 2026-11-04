package control

import (
	"crypto/ecdh"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type session struct {
	csrf    string
	expires time.Time
}
type loginRate struct {
	count int
	reset time.Time
}

type Server struct {
	mu               sync.Mutex
	path             string
	key              ed25519.PrivateKey
	adminHash        [32]byte
	state            diskState
	sessions         map[string]session
	loginRates       map[string]loginRate
	NodeStatusPath   string
	PublicURL        string
	MaxActiveDevices int
}

func Open(path, adminSecret string) (*Server, error) {
	if len(adminSecret) < 24 {
		return nil, errors.New("admin secret must contain at least 24 characters")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return nil, err
	}
	s := &Server{path: path, adminHash: sha256.Sum256([]byte(adminSecret)), sessions: map[string]session{}, loginRates: map[string]loginRate{}}
	seed, err := os.ReadFile(path + ".signing")
	if errors.Is(err, os.ErrNotExist) {
		seed = make([]byte, ed25519.SeedSize)
		if _, err = rand.Read(seed); err == nil {
			err = atomicWrite(path+".signing", seed)
		}
	}
	if err != nil {
		return nil, err
	}
	if len(seed) != ed25519.SeedSize {
		return nil, errors.New("invalid signing key file")
	}
	s.key = ed25519.NewKeyFromSeed(seed)
	s.state = diskState{Version: 1, Groups: []Group{}, Devices: map[string]*Device{}}
	b, err := os.ReadFile(path)
	if err == nil {
		err = json.Unmarshal(b, &s.state)
	} else if errors.Is(err, os.ErrNotExist) {
		err = nil
	}
	if err != nil {
		return nil, err
	}
	if s.state.Devices == nil {
		s.state.Devices = map[string]*Device{}
	}
	if s.state.Nodes == nil {
		s.state.Nodes = map[string]*Node{}
	}
	s.bump()
	if err := s.save(); err != nil {
		return nil, err
	}
	return s, nil
}

func (s *Server) PublicKey() string {
	return base64.RawURLEncoding.EncodeToString(s.key.Public().(ed25519.PublicKey))
}
func (s *Server) bump() {
	s.state.Version++
	if now := time.Now().UnixMilli(); now > s.state.Version {
		s.state.Version = now
	}
}
func (s *Server) save() error {
	b, err := json.MarshalIndent(s.state, "", "  ")
	if err != nil {
		return err
	}
	return atomicWrite(s.path, b)
}

func atomicWrite(path string, data []byte) error {
	f, err := os.OpenFile(path+".tmp", os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0600)
	if err != nil {
		return err
	}
	if _, err = f.Write(data); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	return os.Rename(path+".tmp", path)
}

func randomToken(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}
func tokenHash(token string) string {
	h := sha256.Sum256([]byte(token))
	return hex.EncodeToString(h[:])
}

func (s *Server) addDevice(name, group string) (Invite, error) {
	if s.MaxActiveDevices > 0 {
		count := 0
		for _, device := range s.state.Devices {
			if device.Enabled {
				count++
			}
		}
		if count >= s.MaxActiveDevices {
			return Invite{}, errors.New("active device limit reached; revoke an unused device first")
		}
	}
	if len(strings.TrimSpace(name)) == 0 || len(name) > 100 {
		return Invite{}, errors.New("device name is required (up to 100 characters)")
	}
	if s.group(group) == nil {
		return Invite{}, errors.New("unknown group")
	}
	if len(s.state.Devices) >= 200 {
		return Invite{}, errors.New("device limit reached")
	}
	id, err := randomToken(12)
	if err != nil {
		return Invite{}, err
	}
	token, err := randomToken(32)
	if err != nil {
		return Invite{}, err
	}
	key, err := ecdh.X25519().GenerateKey(rand.Reader)
	if err != nil {
		return Invite{}, err
	}
	dnsKey, err := randomToken(24)
	if err != nil {
		return Invite{}, err
	}
	u := make([]byte, 16)
	if _, err := rand.Read(u); err != nil {
		return Invite{}, err
	}
	u[6] = (u[6] & 0x0f) | 0x40
	u[8] = (u[8] & 0x3f) | 0x80
	s.state.NextDevice++
	d := &Device{ID: id, Name: strings.TrimSpace(name), Group: group, Enabled: true, TokenHash: tokenHash(token),
		UUID:      fmt.Sprintf("%x-%x-%x-%x-%x", u[0:4], u[4:6], u[6:8], u[8:10], u[10:16]),
		WGPrivate: base64.StdEncoding.EncodeToString(key.Bytes()), WGPublic: base64.StdEncoding.EncodeToString(key.PublicKey().Bytes()),
		WGIPv4: fmt.Sprintf("10.70.%d.%d", s.state.NextDevice/250, s.state.NextDevice%250+2), DNSKey: dnsKey, DNSPort: 54000 + s.state.NextDevice}
	s.state.Devices[id] = d
	return Invite{DeviceID: id, Token: token, PublicKey: s.PublicKey()}, nil
}

func (s *Server) group(id string) *Group {
	for i := range s.state.Groups {
		if s.state.Groups[i].ID == id {
			return &s.state.Groups[i]
		}
	}
	return nil
}

func (s *Server) addNode(name, group string) (NodeInvite, error) {
	if strings.TrimSpace(name) == "" || len(name) > 100 || s.group(group) == nil {
		return NodeInvite{}, errors.New("node requires a name and an existing group")
	}
	if len(s.state.Nodes) >= 64 {
		return NodeInvite{}, errors.New("node limit reached")
	}
	id, err := randomToken(12)
	if err != nil {
		return NodeInvite{}, err
	}
	token, err := randomToken(32)
	if err != nil {
		return NodeInvite{}, err
	}
	s.state.Nodes[id] = &Node{ID: id, Name: strings.TrimSpace(name), Group: group, Enabled: true, TokenHash: tokenHash(token)}
	return NodeInvite{NodeID: id, Token: token, PublicKey: s.PublicKey()}, nil
}

func validateGroups(groups []Group) error {
	if len(groups) > 16 {
		return errors.New("maximum 16 groups")
	}
	ids := map[string]bool{}
	for _, g := range groups {
		if len(g.ID) == 0 || len(g.ID) > 64 || ids[g.ID] || len(g.Name) == 0 || len(g.Name) > 100 || len(g.Calls) > 8 || len(g.Profiles) == 0 || len(g.Profiles) > 3 {
			return errors.New("invalid group")
		}
		ids[g.ID] = true
		for _, c := range g.Calls {
			u, err := url.Parse(c)
			if err != nil || u.Scheme != "https" || (u.Host != "vk.ru" && u.Host != "vk.com") || !strings.HasPrefix(u.Path, "/call/join/") || u.User != nil || u.Fragment != "" {
				return errors.New("call links must be HTTPS VK call/join links")
			}
		}
		for mode, p := range g.Profiles {
			if mode != "direct" && mode != "vk" && mode != "dns" {
				return errors.New("unknown profile mode")
			}
			var config map[string]any
			if len(p) > 512*1024 || json.Unmarshal(p, &config) != nil {
				return errors.New("profile must be a JSON object")
			}
			proxies, ok := config["proxies"].([]any)
			if !ok || len(proxies) == 0 {
				return errors.New("profile requires proxies")
			}
			for _, entry := range proxies {
				proxy, ok := entry.(map[string]any)
				if !ok {
					return errors.New("invalid proxy")
				}
				if proxy["name"] == nil || proxy["type"] == nil {
					return errors.New("proxy requires name and type")
				}
				if mode != "direct" {
					meta, ok := proxy["x-vpnn"].(map[string]any)
					if !ok || meta["mode"] != mode || proxy["server"] != "127.0.0.1" {
						return errors.New("embedded profiles require matching x-vpnn metadata and loopback endpoint")
					}
				}
			}
		}
	}
	return nil
}

func (s *Server) payload(d *Device) (Payload, error) {
	g := s.group(d.Group)
	if g == nil {
		return Payload{}, errors.New("device group is unavailable")
	}
	now := time.Now().Unix()
	p := Payload{Schema: 1, DeviceID: d.ID, Version: s.state.Version, IssuedAt: now, ExpiresAt: now + 7*24*3600, Profiles: []Profile{}}
	p.RefreshAfter = now + 6*3600
	if s.PublicURL != "" {
		p.ControlEndpoints = []string{s.PublicURL}
	}
	replacements := map[string]string{"${device.id}": d.ID, "${device.uuid}": d.UUID, "${device.wg_private}": d.WGPrivate, "${device.wg_public}": d.WGPublic, "${device.wg_ipv4}": d.WGIPv4, "${device.dns_key}": d.DNSKey, "${device.dns_label}": dnsLabel(d.ID)}
	names := map[string]string{"direct": "Обычный", "vk": "Через VK", "dns": "Через DNS"}
	for _, mode := range []string{"direct", "vk", "dns"} {
		if mode == "vk" && len(g.Calls) == 0 {
			continue
		}
		raw, ok := g.Profiles[mode]
		if !ok {
			continue
		}
		var config map[string]any
		if err := json.Unmarshal(raw, &config); err != nil {
			return Payload{}, err
		}
		config = replaceValues(config, replacements).(map[string]any)
		for _, entry := range config["proxies"].([]any) {
			proxy := entry.(map[string]any)
			if meta, ok := proxy["x-vpnn"].(map[string]any); ok && meta["mode"] == "vk" {
				v, ok := meta["vk"].(map[string]any)
				if !ok {
					return Payload{}, errors.New("missing FreeTurn configuration")
				}
				v["clientId"] = d.ID
				vk, ok := v["vk"].(map[string]any)
				if !ok {
					vk = map[string]any{}
					v["vk"] = vk
				}
				vk["links"] = g.Calls
			}
		}
		data, err := json.Marshal(config)
		if err != nil {
			return Payload{}, err
		}
		p.Profiles = append(p.Profiles, Profile{ID: mode, Name: names[mode], Config: string(data)})
	}
	return p, nil
}

func replaceValues(value any, replacements map[string]string) any {
	switch v := value.(type) {
	case string:
		for old, new := range replacements {
			v = strings.ReplaceAll(v, old, new)
		}
		return v
	case []any:
		for i := range v {
			v[i] = replaceValues(v[i], replacements)
		}
		return v
	case map[string]any:
		for k, x := range v {
			v[k] = replaceValues(x, replacements)
		}
		return v
	default:
		return value
	}
}

func dnsLabel(id string) string {
	h := sha256.Sum256([]byte(id))
	return "d-" + hex.EncodeToString(h[:8])
}
