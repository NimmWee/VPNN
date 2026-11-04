package control

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

func TestOfflineBootstrapBindsInvitationAndConfiguration(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	s.PublicURL = "https://vpn.example.org"
	s.state.Groups = []Group{{ID: "g", Name: "g", Profiles: map[string]json.RawMessage{"direct": json.RawMessage(`{"proxies":[]}`)}}}
	invite, err := s.addDevice("test", "g")
	if err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRequest("GET", "https://vpn.example.org/api/device/bootstrap", nil)
	r.Header.Set("Authorization", "Bearer "+invite.Token)
	w := httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatalf("bootstrap failed: %d", w.Code)
	}
	var bundle struct {
		Format   string   `json:"format"`
		Envelope Envelope `json:"envelope"`
	}
	if json.Unmarshal(w.Body.Bytes(), &bundle) != nil || bundle.Format != "vpnn-bootstrap-v1" {
		t.Fatal("invalid offline format")
	}
	data, _ := base64.RawURLEncoding.DecodeString(bundle.Envelope.Payload)
	signature, _ := base64.RawURLEncoding.DecodeString(bundle.Envelope.Signature)
	if !ed25519.Verify(s.key.Public().(ed25519.PublicKey), data, signature) {
		t.Fatal("unsigned bootstrap")
	}
	var payload struct {
		Kind       string `json:"kind"`
		Enrollment struct {
			Device    string   `json:"device"`
			Token     string   `json:"token"`
			Endpoints []string `json:"endpoints"`
		} `json:"enrollment"`
		Configuration Envelope `json:"configuration"`
	}
	if json.Unmarshal(data, &payload) != nil || payload.Kind != "bootstrap" || payload.Enrollment.Device != invite.DeviceID || payload.Enrollment.Token != invite.Token || len(payload.Enrollment.Endpoints) != 1 || payload.Enrollment.Endpoints[0] != s.PublicURL {
		t.Fatal("bootstrap identity was not bound to its owner")
	}
	inner, _ := base64.RawURLEncoding.DecodeString(payload.Configuration.Payload)
	innerSignature, _ := base64.RawURLEncoding.DecodeString(payload.Configuration.Signature)
	if !ed25519.Verify(s.key.Public().(ed25519.PublicKey), inner, innerSignature) {
		t.Fatal("missing signed configuration")
	}
	s.state.Devices[invite.DeviceID].Enabled = false
	w = httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatal("revoked device exported bootstrap")
	}
}
