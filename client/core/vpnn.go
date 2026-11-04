package core

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"sync/atomic"
	"time"

	"github.com/metacubex/mihomo/constant"
	"github.com/metacubex/mihomo/listener"
	"vpnn.local/engine"
)

var vpnnRuntime engine.Manager
var vpnnConfigured *engine.Config
var vpnnServiceReady atomic.Bool
var vpnnRequiresBind atomic.Bool
var vpnnValidUntil atomic.Int64

func vpnnConfigFromProxies(proxies []map[string]any) (*engine.Config, error) {
	var result *engine.Config
	for _, proxy := range proxies {
		meta, ok := proxy["x-vpnn"]
		if !ok {
			continue
		}
		if result != nil {
			return nil, errors.New("one embedded transport is allowed per profile")
		}
		data, err := json.Marshal(meta)
		if err != nil {
			return nil, err
		}
		var c engine.Config
		decoder := json.NewDecoder(bytes.NewReader(data))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&c); err != nil {
			return nil, errors.New("invalid x-vpnn transport configuration")
		}
		if err := c.Validate(); err != nil {
			return nil, err
		}
		_, port, _ := net.SplitHostPort(c.Listen)
		if proxy["server"] != "127.0.0.1" || fmt.Sprint(proxy["port"]) != port {
			return nil, errors.New("proxy endpoint must match its owned transport listener")
		}
		result = &c
	}
	return result, nil
}

func readVpnnConfig() (*engine.Config, error) {
	raw, err := handleGetConfig(runningConfigPath())
	if err != nil {
		return nil, err
	}
	deadline, err := vpnnAccessDeadline(raw.Proxy)
	if err != nil {
		return nil, err
	}
	if err := validateVpnnDeadline(deadline); err != nil {
		return nil, err
	}
	vpnnValidUntil.Store(deadline)
	return vpnnConfigFromProxies(raw.Proxy)
}

func vpnnAccessDeadline(proxies []map[string]any) (int64, error) {
	var deadline int64
	for _, proxy := range proxies {
		value, ok := proxy["x-vpnn-valid-until"]
		if !ok {
			continue
		}
		var n int64
		switch v := value.(type) {
		case int:
			n = int64(v)
		case int64:
			n = v
		case float64:
			if v != float64(int64(v)) {
				return 0, errors.New("invalid managed profile expiry")
			}
			n = int64(v)
		default:
			return 0, errors.New("invalid managed profile expiry")
		}
		if n <= 0 {
			return 0, errors.New("invalid managed profile expiry")
		}
		if deadline == 0 || n < deadline {
			deadline = n
		}
	}
	return deadline, nil
}

func validateVpnnDeadline(deadline int64) error {
	if deadline != 0 && time.Now().Unix() >= deadline {
		return errors.New("VPNN configuration expired; refresh settings")
	}
	return nil
}

func profileHasVpnnMetadata() bool {
	b, err := os.ReadFile(runningConfigPath())
	return err == nil && bytes.Contains(b, []byte("x-vpnn"))
}

func startConfiguredVpnn() error {
	if err := validateVpnnDeadline(vpnnValidUntil.Load()); err != nil {
		return err
	}
	if vpnnConfigured == nil {
		return vpnnRuntime.Stop()
	}
	if runtime.GOOS == "android" && !vpnnServiceReady.Load() {
		return nil
	}
	config := *vpnnConfigured
	if config.DNS != nil && config.DNS.SystemResolvers {
		dns := *config.DNS
		dns.Resolvers = vpnnDNSResolvers(dns.Resolvers, platformVpnnSystemDNS())
		config.DNS = &dns
	}
	return vpnnRuntime.Start(config, filepath.Join(constant.Path.HomeDir(), "vpnn"), vpnnProtectFD, nil)
}

func stopVpnn() bool {
	vpnnServiceReady.Store(false)
	if err := vpnnRuntime.Stop(); err != nil {
		logError("embedded transport stop failed: %v", err)
		return false
	}
	return true
}

func failClosedVpnn(err error) error {
	isRunning.Store(false)
	listener.StopListener()
	stopVpnn()
	return err
}

// Android calls this only after its managed service has established the TUN/protect callback.
func StartTransport() bool {
	configMu.Lock()
	defer configMu.Unlock()
	vpnnServiceReady.Store(true)
	if err := startConfiguredVpnn(); err != nil {
		failClosedVpnn(err)
		logError("embedded transport start failed: %v", err)
		return false
	}
	return true
}

type managedVpnnStatus struct {
	engine.Status
	CaptureReady bool              `json:"captureReady"`
	Counters     map[string]uint64 `json:"counters,omitempty"`
}

func handleVpnnStatus() managedVpnnStatus {
	configMu.Lock()
	defer configMu.Unlock()
	ready := isRunning.Load()
	if runtime.GOOS == "windows" {
		ready = ready && listener.GetTunConf().Enable
	} else if runtime.GOOS == "android" {
		ready = ready && vpnnServiceReady.Load()
	}
	return managedVpnnStatus{Status: vpnnRuntime.Status(), CaptureReady: ready, Counters: vpnnRuntime.Diagnostics()}
}
