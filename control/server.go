package control

import (
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/subtle"
	"embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

//go:embed web/*
var web embed.FS

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func fail(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}
func decode(w http.ResponseWriter, r *http.Request, value any) error {
	r.Body = http.MaxBytesReader(w, r.Body, 1024*1024)
	d := json.NewDecoder(r.Body)
	d.DisallowUnknownFields()
	if err := d.Decode(value); err != nil {
		return err
	}
	if err := d.Decode(new(any)); !errors.Is(err, io.EOF) {
		return errors.New("one JSON value required")
	}
	return nil
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { writeJSON(w, 200, map[string]string{"status": "ok"}) })
	mux.HandleFunc("POST /api/admin/login", s.login)
	mux.HandleFunc("/api/admin/", s.admin)
	mux.HandleFunc("GET /api/device/config", s.deviceConfig)
	mux.HandleFunc("GET /api/device/bootstrap", s.deviceBootstrap)
	mux.HandleFunc("GET /api/node/provision", s.nodeProvision)
	files, _ := fs.Sub(web, "web")
	mux.Handle("/", http.FileServer(http.FS(files)))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
		mux.ServeHTTP(w, r)
	})
}

func (s *Server) isAdminToken(r *http.Request) bool {
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	h := sha256.Sum256([]byte(token))
	return subtle.ConstantTimeCompare(h[:], s.adminHash[:]) == 1
}

func (s *Server) login(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Token string `json:"token"`
	}
	if decode(w, r, &body) != nil {
		fail(w, 400, "invalid login request")
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	peer, _, _ := net.SplitHostPort(r.RemoteAddr)
	host := peer
	if ip := net.ParseIP(peer); ip != nil && ip.IsLoopback() {
		if forwarded := net.ParseIP(r.Header.Get("X-Real-IP")); forwarded != nil {
			host = forwarded.String()
		}
	}
	now := time.Now()
	rate := s.loginRates[host]
	if now.After(rate.reset) {
		rate = loginRate{reset: now.Add(15 * time.Minute)}
	}
	if rate.count >= 5 {
		fail(w, 429, "too many login attempts; retry later")
		return
	}
	h := sha256.Sum256([]byte(body.Token))
	if subtle.ConstantTimeCompare(h[:], s.adminHash[:]) != 1 {
		rate.count++
		s.loginRates[host] = rate
		fail(w, 401, "invalid credentials")
		return
	}
	delete(s.loginRates, host)
	for k, v := range s.sessions {
		if now.After(v.expires) {
			delete(s.sessions, k)
		}
	}
	if len(s.sessions) >= 100 {
		fail(w, 429, "session limit reached")
		return
	}
	token, err := randomToken(32)
	if err != nil {
		fail(w, 500, "cannot create session")
		return
	}
	csrf, err := randomToken(32)
	if err != nil {
		fail(w, 500, "cannot create session")
		return
	}
	s.sessions[tokenHash(token)] = session{csrf: csrf, expires: now.Add(12 * time.Hour)}
	secure := r.TLS != nil
	if ip := net.ParseIP(peer); ip != nil && ip.IsLoopback() && r.Header.Get("X-Forwarded-Proto") == "https" {
		secure = true
	}
	http.SetCookie(w, &http.Cookie{Name: "vpnn_admin", Value: token, Path: "/api/admin/", HttpOnly: true, Secure: secure, SameSite: http.SameSiteStrictMode, MaxAge: 12 * 3600})
	writeJSON(w, 200, map[string]string{"csrf": csrf})
}

func (s *Server) admin(w http.ResponseWriter, r *http.Request) {
	s.mu.Lock()
	defer s.mu.Unlock()
	bearer := s.isAdminToken(r)
	var sess session
	if !bearer {
		cookie, err := r.Cookie("vpnn_admin")
		if err != nil {
			fail(w, 401, "administrator login required")
			return
		}
		var ok bool
		sess, ok = s.sessions[tokenHash(cookie.Value)]
		if !ok || time.Now().After(sess.expires) {
			fail(w, 401, "administrator login required")
			return
		}
	}
	if r.Method != "GET" && !bearer {
		if subtle.ConstantTimeCompare([]byte(r.Header.Get("X-CSRF-Token")), []byte(sess.csrf)) != 1 {
			fail(w, 403, "CSRF check failed")
			return
		}
		if origin := r.Header.Get("Origin"); origin != "" {
			u, err := url.Parse(origin)
			if err != nil || u.Host != r.Host {
				fail(w, 403, "origin check failed")
				return
			}
		}
	}
	path := strings.TrimPrefix(r.URL.Path, "/api/admin/")
	if r.Method == "GET" && path == "state" {
		devices := make([]map[string]any, 0, len(s.state.Devices))
		for _, d := range s.state.Devices {
			devices = append(devices, map[string]any{"id": d.ID, "name": d.Name, "group": d.Group, "enabled": d.Enabled, "wgPublic": d.WGPublic, "wgIPv4": d.WGIPv4, "uuid": d.UUID, "lastSeen": d.LastSeen, "ackVersion": d.AckVersion})
		}
		nodes := []map[string]any{}
		for _, node := range s.state.Nodes {
			nodes = append(nodes, map[string]any{"id": node.ID, "name": node.Name, "group": node.Group, "enabled": node.Enabled, "lastSeen": node.LastSeen, "ackVersion": node.AckVersion})
		}
		writeJSON(w, 200, map[string]any{"version": s.state.Version, "publicKey": s.PublicKey(), "groups": s.state.Groups, "devices": devices, "nodes": nodes, "csrf": sess.csrf, "networkStatus": s.networkStatus(), "maxActiveDevices": s.MaxActiveDevices})
		return
	}
	if r.Method == "GET" && path == "provision" {
		active := []map[string]any{}
		for _, d := range s.state.Devices {
			if d.Enabled {
				active = append(active, map[string]any{"id": d.ID, "group": d.Group, "uuid": d.UUID, "wgPublic": d.WGPublic, "wgIPv4": d.WGIPv4, "dnsLabel": dnsLabel(d.ID), "dnsKey": d.DNSKey, "dnsPort": d.DNSPort})
			}
		}
		writeJSON(w, 200, map[string]any{"version": s.state.Version, "devices": active})
		return
	}
	if r.Method == "POST" && path == "logout" {
		if cookie, err := r.Cookie("vpnn_admin"); err == nil {
			delete(s.sessions, tokenHash(cookie.Value))
		}
		http.SetCookie(w, &http.Cookie{Name: "vpnn_admin", Value: "", Path: "/api/admin/", HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: -1})
		writeJSON(w, 200, map[string]bool{"ok": true})
		return
	}
	before, _ := json.Marshal(s.state)
	var result any = map[string]bool{"ok": true}
	status := 200
	switch {
	case r.Method == "PUT" && path == "groups":
		var groups []Group
		if decode(w, r, &groups) != nil || validateGroups(groups) != nil {
			fail(w, 400, "invalid groups or profile configuration")
			return
		}
		ids := map[string]bool{}
		for _, g := range groups {
			ids[g.ID] = true
		}
		for _, d := range s.state.Devices {
			if d.Enabled && !ids[d.Group] {
				fail(w, 409, "an enabled device still uses a removed group")
				return
			}
		}
		s.state.Groups = groups
	case r.Method == "POST" && path == "devices":
		var body struct {
			Name  string `json:"name"`
			Group string `json:"group"`
		}
		if decode(w, r, &body) != nil {
			fail(w, 400, "invalid device request")
			return
		}
		invite, err := s.addDevice(body.Name, body.Group)
		if err != nil {
			fail(w, 400, err.Error())
			return
		}
		result = invite
		status = 201
	case r.Method == "POST" && path == "nodes":
		var body struct {
			Name  string `json:"name"`
			Group string `json:"group"`
		}
		if decode(w, r, &body) != nil {
			fail(w, 400, "invalid node request")
			return
		}
		invite, err := s.addNode(body.Name, body.Group)
		if err != nil {
			fail(w, 400, err.Error())
			return
		}
		result = invite
		status = 201
	case r.Method == "POST" && strings.HasPrefix(path, "nodes/") && strings.HasSuffix(path, "/revoke"):
		id := strings.TrimSuffix(strings.TrimPrefix(path, "nodes/"), "/revoke")
		node, ok := s.state.Nodes[id]
		if !ok {
			fail(w, 404, "node not found")
			return
		}
		node.Enabled = false
	case r.Method == "POST" && strings.HasPrefix(path, "devices/") && strings.HasSuffix(path, "/revoke"):
		id := strings.TrimSuffix(strings.TrimPrefix(path, "devices/"), "/revoke")
		d, ok := s.state.Devices[id]
		if !ok {
			fail(w, 404, "device not found")
			return
		}
		d.Enabled = false
	default:
		fail(w, 404, "endpoint not found")
		return
	}
	s.bump()
	if err := s.save(); err != nil {
		_ = json.Unmarshal(before, &s.state)
		fail(w, 500, "state was not persisted; change rejected")
		return
	}
	writeJSON(w, status, result)
}

func (s *Server) nodeProvision(w http.ResponseWriter, r *http.Request) {
	if r.URL.RawQuery != "" {
		fail(w, 400, "tokens must not be included in URLs")
		return
	}
	hash := tokenHash(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
	s.mu.Lock()
	defer s.mu.Unlock()
	var node *Node
	for _, entry := range s.state.Nodes {
		if subtle.ConstantTimeCompare([]byte(hash), []byte(entry.TokenHash)) == 1 {
			node = entry
			break
		}
	}
	if node == nil {
		fail(w, 401, "invalid node credentials")
		return
	}
	if !node.Enabled {
		fail(w, 403, "node access revoked")
		return
	}
	now := time.Now().Unix()
	payload := NodePayload{Schema: 1, NodeID: node.ID, Group: node.Group, Version: s.state.Version, IssuedAt: now, ExpiresAt: now + 10*60, Devices: []NodeDevice{}}
	for _, device := range s.state.Devices {
		if device.Enabled && device.Group == node.Group {
			payload.Devices = append(payload.Devices, NodeDevice{ID: device.ID, UUID: device.UUID, DNSLabel: dnsLabel(device.ID), DNSKey: device.DNSKey, DNSPort: device.DNSPort})
		}
	}
	data, err := json.Marshal(payload)
	if err != nil {
		fail(w, 500, "provision encoding failed")
		return
	}
	node.LastSeen = now
	if version, err := strconv.ParseInt(r.Header.Get("X-VPNN-Version"), 10, 64); err == nil && version > 0 && version <= s.state.Version {
		node.AckVersion = version
	}
	writeJSON(w, 200, Envelope{Payload: base64.RawURLEncoding.EncodeToString(data), Signature: base64.RawURLEncoding.EncodeToString(ed25519.Sign(s.key, data))})
}

func (s *Server) deviceConfig(w http.ResponseWriter, r *http.Request) {
	if r.URL.RawQuery != "" {
		fail(w, 400, "put the device token in Authorization, not the URL")
		return
	}
	hash := tokenHash(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
	s.mu.Lock()
	defer s.mu.Unlock()
	var device *Device
	for _, d := range s.state.Devices {
		if subtle.ConstantTimeCompare([]byte(hash), []byte(d.TokenHash)) == 1 {
			device = d
			break
		}
	}
	if device == nil {
		fail(w, 401, "invalid device credentials")
		return
	}
	if !device.Enabled {
		nonce := r.Header.Get("X-VPNN-Nonce")
		if decoded, err := base64.RawURLEncoding.DecodeString(nonce); err == nil && len(decoded) == 32 {
			now := time.Now().Unix()
			data, _ := json.Marshal(map[string]any{"schema": 1, "kind": "revocation", "deviceId": device.ID, "version": s.state.Version, "issuedAt": now, "expiresAt": now + 300, "nonce": nonce})
			signature := ed25519.Sign(s.key, data)
			writeJSON(w, 403, Envelope{Payload: base64.RawURLEncoding.EncodeToString(data), Signature: base64.RawURLEncoding.EncodeToString(signature)})
			return
		}
		fail(w, 403, "device access revoked")
		return
	}
	payload, err := s.payload(device)
	if err != nil {
		fail(w, 409, "device configuration is not ready")
		return
	}
	data, err := json.Marshal(payload)
	if err != nil {
		fail(w, 500, "configuration encoding failed")
		return
	}
	device.LastSeen = time.Now().Unix()
	if v, err := strconv.ParseInt(r.Header.Get("X-VPNN-Version"), 10, 64); err == nil && v > 0 && v <= s.state.Version {
		device.AckVersion = v
	}
	signature := ed25519.Sign(s.key, data)
	writeJSON(w, 200, Envelope{Payload: base64.RawURLEncoding.EncodeToString(data), Signature: base64.RawURLEncoding.EncodeToString(signature)})
}
