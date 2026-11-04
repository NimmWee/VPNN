package engine

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"net"
	"path/filepath"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	free "github.com/samosvalishe/free-turn-proxy/mobile"
	dns "masterdnsvpn-go/vpnn"
)

type Status struct {
	Mode       string `json:"mode"`
	State      string `json:"state"`
	Error      string `json:"error,omitempty"`
	CaptchaURL string `json:"captchaUrl,omitempty"`
	Streams    int    `json:"streams,omitempty"`
	Total      int    `json:"total,omitempty"`
}

type Manager struct {
	mu             sync.Mutex
	status         atomic.Pointer[Status]
	generation     atomic.Uint64
	fingerprint    [32]byte
	stop           func() error
	startupTimeout time.Duration
	diagnostics    func() map[string]uint64
}

func (m *Manager) Status() Status {
	if s := m.status.Load(); s != nil {
		return *s
	}
	return Status{State: "idle"}
}

func (m *Manager) Diagnostics() map[string]uint64 {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.diagnostics != nil {
		return m.diagnostics()
	}
	if m.Status().Mode == "vk" {
		s := free.GetState()
		return map[string]uint64{"vkTxBytes": uint64(max(0, s.TxTotal)), "vkRxBytes": uint64(max(0, s.RxTotal)), "vkStreams": uint64(max(0, s.Streams)), "vkTotal": uint64(max(0, s.Total))}
	}
	return nil
}

func (m *Manager) Start(c Config, stateDir string, protect func(int) bool, notify func(Status)) error {
	return m.StartMeasurement(c, stateDir, protect, notify, 0, 0)
}

func (m *Manager) StartMeasurement(c Config, stateDir string, protect func(int) bool, notify func(Status), downloadMTU, duplication int) error {
	if downloadMTU != 0 && (downloadMTU < 500 || downloadMTU > 1232) || duplication < 0 || duplication > 2 {
		return errors.New("invalid DNS measurement options")
	}
	if err := c.Validate(); err != nil {
		return err
	}
	data, _ := json.Marshal(struct {
		Config      Config
		DownloadMTU int
		Duplication int
	}{c, downloadMTU, duplication})
	fingerprint := sha256.Sum256(data)
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.stop != nil && m.fingerprint == fingerprint {
		return nil
	}
	if err := m.stopLocked(); err != nil {
		return err
	}
	generation := m.generation.Add(1)
	update := func(s Status) {
		if m.generation.Load() != generation {
			return
		}
		s.Mode = c.Mode
		m.status.Store(&s)
		if notify != nil {
			notify(s)
		}
	}
	update(Status{State: "connecting"})
	switch c.Mode {
	case "vk":
		free.SetStateDir(filepath.Join(stateDir, "vk"))
		free.SetProtect(protector{protect})
		free.SetEventSink(&eventSink{update: update})
		raw, err := c.VKJSON()
		if err == nil {
			err = free.Start(string(raw))
		}
		if err != nil {
			update(Status{State: "error", Error: "FreeTurn startup failed: " + err.Error()})
			return err
		}
		m.stop = func() error { free.Stop(); free.SetEventSink(nil); free.SetProtect(nil); return nil }
	case "dns":
		_, port, _ := net.SplitHostPort(c.Listen)
		p, _ := strconv.Atoi(port)
		d, err := dns.NewForMeasurement(c.DNS.Domains, c.DNS.Resolvers, c.DNS.Key, c.DNS.Encryption, p, filepath.Join(stateDir, "dns"), protect, downloadMTU, duplication)
		if err != nil {
			update(Status{State: "error", Error: "DNS startup failed: " + err.Error()})
			return err
		}
		m.diagnostics = d.Diagnostics
		ctx, cancel := context.WithCancel(context.Background())
		done := make(chan struct{})
		go func() {
			defer close(done)
			if err := d.Run(ctx); err != nil && ctx.Err() == nil {
				update(Status{State: "error", Error: "DNS runtime stopped"})
			}
		}()
		go func() {
			ticker := time.NewTicker(250 * time.Millisecond)
			defer ticker.Stop()
			timeout := m.startupTimeout
			if timeout <= 0 {
				timeout = 90 * time.Second
			}
			deadline := time.NewTimer(timeout)
			defer deadline.Stop()
			for {
				select {
				case <-ctx.Done():
					return
				case <-done:
					if ctx.Err() == nil {
						update(Status{State: "error", Error: "DNS runtime stopped before its listener became ready"})
					}
					return
				case <-deadline.C:
					update(Status{State: "error", Error: "DNS startup timed out; check resolver reachability and server settings"})
					cancel()
					return
				case <-ticker.C:
					conn, err := net.DialTimeout("tcp", c.Listen, 100*time.Millisecond)
					if err == nil {
						conn.Close()
						update(Status{State: "ready"})
						return
					}
				}
			}
		}()
		m.stop = func() error {
			cancel()
			select {
			case <-done:
				return nil
			case <-time.After(15 * time.Second):
				return errors.New("DNS transport did not stop; refusing overlapping runtime")
			}
		}
	}
	m.fingerprint = fingerprint
	return nil
}

func (m *Manager) Stop() error { m.mu.Lock(); defer m.mu.Unlock(); return m.stopLocked() }

func (m *Manager) stopLocked() error {
	if m.stop != nil {
		if err := m.stop(); err != nil {
			return err
		}
		m.stop = nil
	}
	m.generation.Add(1)
	m.diagnostics = nil
	m.status.Store(&Status{State: "idle"})
	return nil
}

type protector struct{ run func(int) bool }

func (p protector) Protect(fd int) bool { return p.run == nil || p.run(fd) }

type eventSink struct {
	mu         sync.Mutex
	update     func(Status)
	captchaURL string
}

func (e *eventSink) OnState(state string, streams, total int, _ string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	s := Status{State: state, Streams: streams, Total: total}
	if state == "captcha" {
		s.CaptchaURL = e.captchaURL
	}
	if state == "error" {
		s.Error = "FreeTurn connection failed; check server parameters or complete manual CAPTCHA"
	}
	e.update(s)
}
func (e *eventSink) OnLog(_, _ string, _ int64) {}
func (e *eventSink) OnCaptcha(url string, manual bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if url == "" {
		e.captchaURL = ""
		e.update(Status{State: "connecting"})
		return
	}
	if manual {
		e.captchaURL = url
		e.update(Status{State: "captcha", CaptchaURL: url})
	}
}
