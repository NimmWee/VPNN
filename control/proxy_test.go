package control

import (
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
)

func TestTrustedLoopbackProxySeparatesLoginLimits(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	h := s.Handler()
	for i := 0; i < 6; i++ {
		r := httptest.NewRequest("POST", "http://vpn.example/api/admin/login", strings.NewReader(`{"token":"wrong"}`))
		r.RemoteAddr = "127.0.0.1:1234"
		r.Header.Set("X-Real-IP", "192.0.2.1")
		h.ServeHTTP(httptest.NewRecorder(), r)
	}
	r := httptest.NewRequest("POST", "http://vpn.example/api/admin/login", strings.NewReader(`{"token":"`+strings.Repeat("s", 32)+`"}`))
	r.RemoteAddr = "127.0.0.1:1234"
	r.Header.Set("X-Real-IP", "192.0.2.2")
	r.Header.Set("X-Forwarded-Proto", "https")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatalf("another client behind nginx was blocked: %d", w.Code)
	}
	if !w.Result().Cookies()[0].Secure {
		t.Fatal("HTTPS proxy session cookie is not secure")
	}
}

func TestPublicPeerCannotSpoofProxyLoginAddress(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 6; i++ {
		r := httptest.NewRequest("POST", "http://vpn.example/api/admin/login", strings.NewReader(`{"token":"wrong"}`))
		r.RemoteAddr = "192.0.2.1:1234"
		r.Header.Set("X-Real-IP", "192.0.2."+string(rune('2'+i)))
		w := httptest.NewRecorder()
		s.Handler().ServeHTTP(w, r)
		if i == 5 && w.Code != 429 {
			t.Fatal("public peer bypassed rate limit with an untrusted header")
		}
	}
}
