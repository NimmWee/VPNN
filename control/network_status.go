package control

import (
	"encoding/json"
	"io"
	"os"
	"time"
)

type NetworkStatus struct {
	Healthy        bool     `json:"healthy"`
	AppliedVersion int64    `json:"appliedVersion,omitempty"`
	AppliedAt      int64    `json:"appliedAt,omitempty"`
	Devices        []string `json:"devices,omitempty"`
	VKDevices      int      `json:"vkDevices"`
	DNSDevices     int      `json:"dnsDevices"`
	Error          string   `json:"error,omitempty"`
}

func (s *Server) networkStatus() *NetworkStatus {
	if s.NodeStatusPath == "" {
		return nil
	}
	file, err := os.Open(s.NodeStatusPath)
	if err != nil {
		return &NetworkStatus{Error: "Node status unavailable"}
	}
	defer file.Close()
	status := &NetworkStatus{}
	if json.NewDecoder(io.LimitReader(file, 64000)).Decode(status) != nil {
		return &NetworkStatus{Error: "Invalid node status"}
	}
	// The co-located reconciler updates this heartbeat every ten seconds.
	// A stopped reconciler must not leave the administrator looking at old success.
	if status.Healthy && (status.AppliedAt <= 0 || time.Now().Unix()-status.AppliedAt > 45 || status.AppliedAt-time.Now().Unix() > 30) {
		status.Healthy = false
		status.Error = "Node heartbeat is stale"
	}
	return status
}
