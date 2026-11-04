package vkauth

import (
	"crypto/sha256"
	"encoding/json"
	"sync"
	"time"
)

const retainedStoreLimit = 32

var retainedStores = struct {
	sync.Mutex
	entries map[[32]byte]retainedStore
}{entries: make(map[[32]byte]retainedStore)}

type retainedStore struct {
	store *Store
	used  time.Time
}

func reconnectStore(cfg Config) *Store {
	if cfg.FingerprintSeed == "" {
		return NewStore(cfg.StreamsPerCache)
	}
	data, _ := json.Marshal(struct {
		Seed, Link       string
		Platform         any
		Paths            []string
		Credentials      []VKCredentials
		Streams          int
		Manual, Advanced bool
	}{cfg.FingerprintSeed, cfg.Link, cfg.Platform, cfg.StatePaths, cfg.Credentials, cfg.StreamsPerCache, cfg.ManualOnly, cfg.AdvancedCaptcha})
	key := sha256.Sum256(data)
	now := time.Now()
	retainedStores.Lock()
	defer retainedStores.Unlock()
	for id, entry := range retainedStores.entries {
		if now.Sub(entry.used) > CredentialLifetime && !entry.store.hasValidCredentials(now) {
			delete(retainedStores.entries, id)
		}
	}
	if entry, ok := retainedStores.entries[key]; ok {
		entry.used = now
		retainedStores.entries[key] = entry
		return entry.store
	}
	if len(retainedStores.entries) >= retainedStoreLimit {
		var oldest [32]byte
		oldestTime := now.Add(time.Second)
		for id, entry := range retainedStores.entries {
			if entry.used.Before(oldestTime) {
				oldest, oldestTime = id, entry.used
			}
		}
		delete(retainedStores.entries, oldest)
	}
	store := NewStore(cfg.StreamsPerCache)
	retainedStores.entries[key] = retainedStore{store: store, used: now}
	return store
}

func (s *Store) hasValidCredentials(now time.Time) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, cache := range s.caches {
		cache.mutex.RLock()
		valid := now.Before(cache.creds.ExpiresAt) && len(cache.creds.ServerAddrs) > 0
		cache.mutex.RUnlock()
		if valid {
			return true
		}
	}
	return false
}
