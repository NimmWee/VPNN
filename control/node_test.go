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

func TestNodeTokenIsReadOnlyScopedAndProvisionIsSigned(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	s.state.Groups = []Group{{ID: "one", Name: "one"}, {ID: "two", Name: "two"}}
	first, _ := s.addDevice("first", "one")
	second, _ := s.addDevice("second", "two")
	node, err := s.addNode("test-node", "one")
	if err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRequest("GET", "http://localhost/api/node/provision", nil)
	r.Header.Set("Authorization", "Bearer "+node.Token)
	w := httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	var envelope Envelope
	json.Unmarshal(w.Body.Bytes(), &envelope)
	payload, _ := base64.RawURLEncoding.DecodeString(envelope.Payload)
	signature, _ := base64.RawURLEncoding.DecodeString(envelope.Signature)
	if !ed25519.Verify(s.key.Public().(ed25519.PublicKey), payload, signature) {
		t.Fatal("unsigned node provisioning")
	}
	if !strings.Contains(string(payload), first.DeviceID) || strings.Contains(string(payload), second.DeviceID) {
		t.Fatal("node escaped its group scope")
	}
	r = httptest.NewRequest("GET", "http://localhost/api/admin/state", nil)
	r.Header.Set("Authorization", "Bearer "+node.Token)
	w = httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 401 {
		t.Fatal("node token granted administrator access")
	}
	s.state.Nodes[node.NodeID].Enabled = false
	r = httptest.NewRequest("GET", "http://localhost/api/node/provision", nil)
	r.Header.Set("Authorization", "Bearer "+node.Token)
	w = httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatal("revoked node token accepted")
	}
}
