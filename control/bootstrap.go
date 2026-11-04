package control

import (
	"crypto/ed25519"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"strings"
)

func (s *Server) signValue(value any) (Envelope, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return Envelope{}, err
	}
	return Envelope{Payload: base64.RawURLEncoding.EncodeToString(data), Signature: base64.RawURLEncoding.EncodeToString(ed25519.Sign(s.key, data))}, nil
}

func (s *Server) deviceBootstrap(w http.ResponseWriter, r *http.Request) {
	if r.URL.RawQuery != "" {
		fail(w, 400, "tokens must not be included in URLs")
		return
	}
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	hash := tokenHash(token)
	s.mu.Lock()
	defer s.mu.Unlock()
	var device *Device
	for _, entry := range s.state.Devices {
		if subtle.ConstantTimeCompare([]byte(hash), []byte(entry.TokenHash)) == 1 {
			device = entry
			break
		}
	}
	if device == nil {
		fail(w, 401, "invalid device credentials")
		return
	}
	if !device.Enabled {
		fail(w, 403, "device access revoked")
		return
	}
	if s.PublicURL == "" {
		fail(w, 409, "public HTTPS URL is not configured")
		return
	}
	configuration, err := s.payload(device)
	if err != nil {
		fail(w, 409, "device configuration is not ready")
		return
	}
	inner, err := s.signValue(configuration)
	if err != nil {
		fail(w, 500, "configuration signing failed")
		return
	}
	outer, err := s.signValue(map[string]any{"schema": 1, "kind": "bootstrap", "enrollment": map[string]any{
		"endpoints": []string{s.PublicURL}, "token": token, "key": s.PublicKey(), "device": device.ID,
	}, "configuration": inner})
	if err != nil {
		fail(w, 500, "bootstrap signing failed")
		return
	}
	writeJSON(w, 200, map[string]any{"format": "vpnn-bootstrap-v1", "envelope": outer})
}
