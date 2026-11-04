package vkauth

import (
	"context"
	"os"
	"testing"
	"time"

	tlsclient "github.com/bogdanfinn/tls-client"
)

func TestReconnectReusesValidCredentialsForSameIdentity(t *testing.T) {
	cfg := Config{FingerprintSeed: t.Name(), StatePaths: []string{t.TempDir()}, StreamsPerCache: 10}
	calls := 0
	fetch := func(context.Context, string, int, VKCredentials, tlsclient.CookieJar) (string, string, []string, error) {
		calls++
		return "test-user", "test-password", []string{"127.0.0.1:3478"}, nil
	}
	first := New(cfg)
	first.tokenChain = fetch
	first.callsChain = nil
	first.minFetchIntervalFn = func() time.Duration { return 0 }
	if _, _, _, err := first.GetCredentials(context.Background(), "test-call", 1); err != nil {
		t.Fatal(err)
	}
	second := New(cfg)
	second.tokenChain = fetch
	second.callsChain = nil
	second.minFetchIntervalFn = func() time.Duration { return 0 }
	if _, _, _, err := second.GetCredentials(context.Background(), "test-call", 1); err != nil {
		t.Fatal(err)
	}
	if calls != 1 {
		t.Fatalf("reconnect repeated VK authentication: got %d requests, want 1", calls)
	}
}

func TestReconnectCacheRejectsExpiredAndInvalidatedCredentials(t *testing.T) {
	cfg := Config{FingerprintSeed: t.Name(), Link: "test-call", StatePaths: []string{t.TempDir()}}
	first := New(cfg)
	first.store.Get(1).store(TurnCredentials{Link: "test-call", Username: "test-user", ServerAddrs: []string{"127.0.0.1:3478"}, ExpiresAt: time.Now().Add(-time.Second)})
	second := New(cfg)
	if _, _, ok := second.store.Get(1).lookup("test-call", 1); ok {
		t.Fatal("expired credential was reused")
	}
	first.store.Get(1).store(TurnCredentials{Link: "test-call", Username: "test-user", ServerAddrs: []string{"127.0.0.1:3478"}, ExpiresAt: time.Now().Add(time.Minute)})
	for range MaxCacheErrors {
		second.HandleAuthError(1)
	}
	third := New(cfg)
	if _, _, ok := third.store.Get(1).lookup("test-call", 1); ok {
		t.Fatal("rejected credential survived reconnect")
	}
	entries, err := os.ReadDir(cfg.StatePaths[0])
	if err != nil || len(entries) != 0 {
		t.Fatal("credential cache must not persist secrets to disk")
	}
}

func TestReconnectCacheIsScopedAndBounded(t *testing.T) {
	cfg := Config{FingerprintSeed: t.Name(), Link: "first-call", StatePaths: []string{t.TempDir()}}
	first := New(cfg)
	first.store.Get(1).store(TurnCredentials{Link: "first-call", Username: "test-user", ServerAddrs: []string{"127.0.0.1:3478"}, ExpiresAt: time.Now().Add(time.Minute)})
	for _, changed := range []Config{
		{FingerprintSeed: "other-device", Link: cfg.Link, StatePaths: cfg.StatePaths},
		{FingerprintSeed: cfg.FingerprintSeed, Link: "other-call", StatePaths: cfg.StatePaths},
		{FingerprintSeed: cfg.FingerprintSeed, Link: cfg.Link, StatePaths: []string{t.TempDir()}},
	} {
		if New(changed).store == first.store {
			t.Fatal("reused credentials across an identity, call or data directory")
		}
	}
	for i := 0; i < retainedStoreLimit+5; i++ {
		changed := cfg
		changed.Link = time.Unix(int64(i), 0).String()
		New(changed)
	}
	retainedStores.Lock()
	defer retainedStores.Unlock()
	if len(retainedStores.entries) > retainedStoreLimit {
		t.Fatal("unbounded retained credential cache")
	}
}
