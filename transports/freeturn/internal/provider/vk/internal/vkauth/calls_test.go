package vkauth

import (
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"testing"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
	tlsclient "github.com/bogdanfinn/tls-client"
)

type callsDoer func(*fhttp.Request) (*fhttp.Response, error)

func (f callsDoer) Do(r *fhttp.Request) (*fhttp.Response, error) { return f(r) }

func TestVKCallsFiveStepChain(t *testing.T) {
	paths := []string{"/method/auth.getAnonymToken", "/method/messages.getCallPreview", "/method/messages.getAnonymCallToken", "/fb.do", "/fb.do"}
	bodies := []string{`{"response":{"token":"anon-secret"}}`, `{"response":{"user_id":-7,"secret":"preview-secret"}}`, `{"response":{"token":"call-secret"}}`, `{"session_key":"session-secret"}`, `{"turn_server":{"username":"test-user","credential":"turn-secret","urls":["turn:192.0.2.1:3478?transport=udp","turn:192.0.2.2:3478?transport=tcp"]}}`}
	count := 0
	device := ""
	doer := callsDoer(func(r *fhttp.Request) (*fhttp.Response, error) {
		i := count
		count++
		if i >= len(paths) {
			t.Fatal("unbounded requests")
		}
		if r.Method != "POST" || r.URL.Path != paths[i] || r.Header.Get("Origin") != "" {
			t.Fatalf("unexpected native request %d", i)
		}
		if i < 3 {
			if r.URL.Host != "api.vk.me" || r.URL.Query().Get("v") != "5.276" {
				t.Fatal("legacy endpoint used")
			}
			if i == 0 {
				device = r.URL.Query().Get("device_id")
			} else if r.URL.Query().Get("device_id") != device {
				t.Fatal("identity changed within flow")
			}
		}
		if i == 2 && (r.URL.Query().Get("anonymous_token") != "anon-secret" || r.URL.Query().Get("secret") != "preview-secret" || r.URL.Query().Get("user_id") != "-7") {
			t.Fatal("preview identity lost")
		}
		if i == 4 && (r.URL.Query().Get("anonymToken") != "call-secret" || r.URL.Query().Get("session_key") != "session-secret") {
			t.Fatal("session identity lost")
		}
		return &fhttp.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(bodies[i]))}, nil
	})
	u, p, a, err := fetchVKCallsCredentials(context.Background(), doer, "test-call", "VPNN-test")
	if err != nil || count != 5 || u != "test-user" || p != "turn-secret" || len(a) != 2 {
		t.Fatalf("chain failed: calls=%d err=%v", count, err)
	}
}

func TestVKCallsStopsOnTerminalAndRedactsErrors(t *testing.T) {
	for _, body := range []string{`{"error":{"error_code":9000,"error_msg":"private-secret"}}`, `{"error":{"error_code":14,"captcha_sid":"private-secret"}}`, strings.Repeat("private-secret", 100000)} {
		count := 0
		doer := callsDoer(func(*fhttp.Request) (*fhttp.Response, error) {
			count++
			return &fhttp.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(body))}, nil
		})
		_, _, _, err := fetchVKCallsCredentials(context.Background(), doer, "private-call", "test")
		if err == nil || count != 1 || strings.Contains(err.Error(), "private") {
			t.Fatalf("unbounded or unredacted error: %v", err)
		}
	}
}

func TestVKCallsPreferredOnceAndTerminalDoesNotFallBack(t *testing.T) {
	for _, terminal := range []bool{false, true} {
		legacy, native := 0, 0
		c := newTestClient(t, func(context.Context, string, int, VKCredentials, tlsclient.CookieJar) (string, string, []string, error) {
			legacy++
			return "legacy", "pass", []string{"192.0.2.1:3478"}, nil
		})
		c.callsChain = func(context.Context, string, tlsclient.CookieJar) (string, string, []string, error) {
			native++
			if terminal {
				return "", "", nil, ErrInvalidJoinLink
			}
			return "", "", nil, errors.New("new API unavailable")
		}
		_, _, _, err := c.GetCredentials(context.Background(), "call", 1)
		if native != 1 || (terminal && (!errors.Is(err, ErrInvalidJoinLink) || legacy != 0)) || (!terminal && (err != nil || legacy != 1)) {
			t.Fatalf("fallback native=%d legacy=%d err=%v", native, legacy, err)
		}
	}
}

func TestCredentialExpiryHonorsServerAndBoundsReuse(t *testing.T) {
	now := time.Now()
	for _, d := range []time.Duration{-time.Minute, 5 * time.Minute, 2 * time.Hour, 48 * time.Hour} {
		expiry := time.Now().Add(d).Truncate(time.Second)
		got := credentialExpiry(fmt.Sprintf("%d:key", expiry.Unix()), now)
		if got.After(expiry.Add(-CacheSafetyMargin)) || got.After(now.Add(8*time.Hour)) {
			t.Fatal("credential expiry extended")
		}
		if d == 2*time.Hour && got.Before(now.Add(time.Hour)) {
			t.Fatal("valid server lifetime unnecessarily reduced to ten minutes")
		}
	}
	if got := credentialExpiry("opaque-user", now); !got.Equal(now.Add(CredentialLifetime - CacheSafetyMargin)) {
		t.Fatal("legacy lifetime changed without server expiry")
	}
}
