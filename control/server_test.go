package control

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"testing"
)

func TestEnrollmentSignedUpdatesIsolationAndRevocation(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	s, err := Open(path, "an-admin-secret-with-enough-entropy-for-tests")
	if err != nil {
		t.Fatal(err)
	}
	ts := httptest.NewServer(s.Handler())
	defer ts.Close()
	request := func(method, path, token string, body any, cookie *http.Cookie, csrf string) (*http.Response, []byte) {
		t.Helper()
		data, _ := json.Marshal(body)
		r, _ := http.NewRequest(method, ts.URL+path, bytes.NewReader(data))
		r.Header.Set("Content-Type", "application/json")
		if token != "" {
			r.Header.Set("Authorization", "Bearer "+token)
		}
		if cookie != nil {
			r.AddCookie(cookie)
		}
		if csrf != "" {
			r.Header.Set("X-CSRF-Token", csrf)
		}
		res, err := http.DefaultClient.Do(r)
		if err != nil {
			t.Fatal(err)
		}
		b, _ := io.ReadAll(res.Body)
		res.Body.Close()
		return res, b
	}
	res, _ := request("GET", "/api/admin/state", "", nil, nil, "")
	if res.StatusCode != 401 {
		t.Fatalf("unauthorized admin status %d", res.StatusCode)
	}
	res, b := request("POST", "/api/admin/login", "", map[string]string{"token": "an-admin-secret-with-enough-entropy-for-tests"}, nil, "")
	if res.StatusCode != 200 || len(res.Cookies()) == 0 {
		t.Fatalf("login failed %d %s", res.StatusCode, b)
	}
	cookie := res.Cookies()[0]
	var login struct {
		CSRF string `json:"csrf"`
	}
	json.Unmarshal(b, &login)
	group := Group{ID: "home", Name: "Дом", Calls: []string{"https://vk.ru/call/join/test-owned-call"}, Profiles: map[string]json.RawMessage{
		"direct": json.RawMessage(`{"proxies":[{"name":"VPNN","type":"vless","server":"example.test","port":443,"uuid":"${device.uuid}"}],"proxy-groups":[{"name":"VPNN mode","type":"select","proxies":["VPNN"]}],"rules":["MATCH,VPNN mode"]}`),
	}}
	res, _ = request("PUT", "/api/admin/groups", "", []Group{group}, cookie, "")
	if res.StatusCode != 403 {
		t.Fatal("mutation accepted without CSRF")
	}
	res, b = request("PUT", "/api/admin/groups", "", []Group{group}, cookie, login.CSRF)
	if res.StatusCode != 200 {
		t.Fatalf("group update %d %s", res.StatusCode, b)
	}
	var invites []Invite
	for _, name := range []string{"first", "second"} {
		res, b = request("POST", "/api/admin/devices", "", map[string]string{"name": name, "group": "home"}, cookie, login.CSRF)
		if res.StatusCode != 201 {
			t.Fatalf("enrollment %d %s", res.StatusCode, b)
		}
		var invite Invite
		if err := json.Unmarshal(b, &invite); err != nil {
			t.Fatal(err)
		}
		invites = append(invites, invite)
	}
	var payloads []Payload
	for _, invite := range invites {
		res, b = request("GET", "/api/device/config", invite.Token, nil, nil, "")
		if res.StatusCode != 200 {
			t.Fatalf("config %d %s", res.StatusCode, b)
		}
		var env Envelope
		json.Unmarshal(b, &env)
		data, _ := base64.RawURLEncoding.DecodeString(env.Payload)
		sig, _ := base64.RawURLEncoding.DecodeString(env.Signature)
		key, _ := base64.RawURLEncoding.DecodeString(invite.PublicKey)
		if !ed25519.Verify(key, data, sig) {
			t.Fatal("invalid signature")
		}
		var payload Payload
		json.Unmarshal(data, &payload)
		if payload.DeviceID != invite.DeviceID || len(payload.Profiles) != 1 {
			t.Fatal("wrong device payload")
		}
		payloads = append(payloads, payload)
	}
	if payloads[0].Profiles[0].Config == payloads[1].Profiles[0].Config {
		t.Fatal("devices shared protocol credentials")
	}
	res, b = request("POST", "/api/admin/devices/"+url.PathEscape(invites[0].DeviceID)+"/revoke", "", nil, cookie, login.CSRF)
	if res.StatusCode != 200 {
		t.Fatalf("revoke %d %s", res.StatusCode, b)
	}
	res, _ = request("GET", "/api/device/config", invites[0].Token, nil, nil, "")
	if res.StatusCode != 403 {
		t.Fatal("revoked token still accepted")
	}
	nonce := base64.RawURLEncoding.EncodeToString(bytes.Repeat([]byte{7}, 32))
	req, _ := http.NewRequest("GET", ts.URL+"/api/device/config", nil)
	req.Header.Set("Authorization", "Bearer "+invites[0].Token)
	req.Header.Set("X-VPNN-Nonce", nonce)
	revokedResponse, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	var receipt Envelope
	json.NewDecoder(revokedResponse.Body).Decode(&receipt)
	revokedResponse.Body.Close()
	data, _ := base64.RawURLEncoding.DecodeString(receipt.Payload)
	sig, _ := base64.RawURLEncoding.DecodeString(receipt.Signature)
	key, _ := base64.RawURLEncoding.DecodeString(invites[0].PublicKey)
	if !ed25519.Verify(key, data, sig) {
		t.Fatal("unsigned revocation")
	}
	var revocation map[string]any
	json.Unmarshal(data, &revocation)
	if revocation["kind"] != "revocation" || revocation["deviceId"] != invites[0].DeviceID || revocation["nonce"] != nonce {
		t.Fatal("revocation not bound to request and device")
	}
	res, _ = request("GET", "/api/device/config", invites[1].Token, nil, nil, "")
	if res.StatusCode != 200 {
		t.Fatal("unrelated device was revoked")
	}
	s2, err := Open(path, "an-admin-secret-with-enough-entropy-for-tests")
	if err != nil {
		t.Fatal(err)
	}
	if s.PublicKey() != s2.PublicKey() {
		t.Fatal("signing identity changed after restart")
	}
}
