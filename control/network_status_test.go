package control

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestStaleNetworkStatusIsNotReportedHealthy(t *testing.T) {
	s := &Server{NodeStatusPath: filepath.Join(t.TempDir(), "node.json")}
	for _, at := range []int64{0, time.Now().Add(-time.Minute).Unix(), time.Now().Add(time.Minute).Unix()} {
		data, _ := json.Marshal(NetworkStatus{Healthy: true, AppliedAt: at, AppliedVersion: 10})
		if err := os.WriteFile(s.NodeStatusPath, data, 0600); err != nil {
			t.Fatal(err)
		}
		if s.networkStatus().Healthy {
			t.Fatal("stale or impossible node heartbeat was shown healthy")
		}
	}
}

func TestNetworkStatusContainsOnlyConfirmedPublicFields(t *testing.T) {
	dir := t.TempDir()
	s, err := Open(filepath.Join(dir, "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	s.NodeStatusPath = filepath.Join(dir, "node.json")
	if s.networkStatus().Healthy {
		t.Fatal("missing status was treated as ready")
	}
	data, _ := json.Marshal(map[string]any{"healthy": true, "appliedAt": time.Now().Unix(), "appliedVersion": 4, "dnsDevices": 2, "dnsKey": "secret"})
	if err := os.WriteFile(s.NodeStatusPath, data, 0600); err != nil {
		t.Fatal(err)
	}
	status := s.networkStatus()
	if !status.Healthy || status.AppliedVersion != 4 || status.Error != "" {
		t.Fatal("valid node report was not accepted")
	}
}

func TestDeviceCapacityCountsOnlyEnabledDevices(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "state.json"), strings.Repeat("s", 32))
	if err != nil {
		t.Fatal(err)
	}
	s.MaxActiveDevices = 1
	s.state.Groups = []Group{{ID: "g", Name: "g"}}
	first, err := s.addDevice("first", "g")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.addDevice("second", "g"); err == nil {
		t.Fatal("node capacity was exceeded")
	}
	s.state.Devices[first.DeviceID].Enabled = false
	if _, err := s.addDevice("second", "g"); err != nil {
		t.Fatal("revoked device still occupied capacity")
	}
}
