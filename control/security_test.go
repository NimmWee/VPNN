package control

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

func TestBadLoginRateLimitAndNoCredentialsInAdminState(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	h := s.Handler()
	for i := 0; i < 6; i++ {
		r := httptest.NewRequest("POST", "http://localhost/api/admin/login", strings.NewReader(`{"token":"wrong"}`))
		r.RemoteAddr = "127.0.0.1:1234"
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		want := 401
		if i == 5 {
			want = 429
		}
		if w.Code != want {
			t.Fatalf("attempt %d got %d", i, w.Code)
		}
	}
	s.mu.Lock()
	s.state.Groups = []Group{{ID: "test", Name: "test"}}
	invite, err := s.addDevice("test", "test")
	s.mu.Unlock()
	if err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRequest("GET", "http://localhost/api/admin/state", nil)
	r.Header.Set("Authorization", "Bearer "+strings.Repeat("s", 32))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatal(w.Code)
	}
	for _, secret := range []string{invite.Token, "tokenHash", "wgPrivate", "dnsKey"} {
		if strings.Contains(w.Body.String(), secret) {
			t.Fatalf("admin overview leaked %s", secret)
		}
	}
}

func TestInvalidPublishIsAtomicAndTokenCannotGoInQuery(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	before := s.state.Version
	r := httptest.NewRequest("PUT", "http://localhost/api/admin/groups", strings.NewReader(`[{"id":"g","name":"g","calls":["http://evil.test/call/join/x"],"profiles":{}}]`))
	r.Header.Set("Authorization", "Bearer "+strings.Repeat("s", 32))
	w := httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 400 || s.state.Version != before || len(s.state.Groups) != 0 {
		t.Fatal("invalid publish modified state")
	}
	r = httptest.NewRequest("GET", "http://localhost/api/device/config?token=secret", nil)
	w = httptest.NewRecorder()
	s.Handler().ServeHTTP(w, r)
	if w.Code != 400 {
		t.Fatal("query token accepted")
	}
}

func TestCrossOriginMutationAndCookieFlags(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	ts := httptest.NewServer(s.Handler())
	defer ts.Close()
	res, err := http.Post(ts.URL+"/api/admin/login", "application/json", strings.NewReader(`{"token":"`+strings.Repeat("s", 32)+`"}`))
	if err != nil {
		t.Fatal(err)
	}
	var login map[string]string
	json.NewDecoder(res.Body).Decode(&login)
	res.Body.Close()
	c := res.Cookies()[0]
	if !c.HttpOnly || c.SameSite != http.SameSiteStrictMode {
		t.Fatal("unsafe cookie")
	}
	r, _ := http.NewRequest("PUT", ts.URL+"/api/admin/groups", bytes.NewBufferString(`[]`))
	r.AddCookie(c)
	r.Header.Set("X-CSRF-Token", login["csrf"])
	r.Header.Set("Origin", "https://evil.test")
	res, err = http.DefaultClient.Do(r)
	if err != nil {
		t.Fatal(err)
	}
	io.Copy(io.Discard, res.Body)
	res.Body.Close()
	if res.StatusCode != 403 {
		t.Fatal("cross-origin mutation accepted")
	}
}

func TestDeviceDNSKeyMatchesServerContract(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	s.state.Groups = []Group{{ID: "g", Name: "g"}}
	invite, err := s.addDevice("test", "g")
	if err != nil {
		t.Fatal(err)
	}
	if len(s.state.Devices[invite.DeviceID].DNSKey) != 32 {
		t.Fatal("MasterDnsVPN AES-256 server requires an exact 32-character key")
	}
}
