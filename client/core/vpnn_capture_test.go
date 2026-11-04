package core

import (
	"encoding/json"
	"testing"
)

func TestVpnnStatusReportsCaptureFalseWhenStopped(t *testing.T) {
	if isRunning.Load() {
		t.Skip("another test owns the running lifecycle")
	}
	data, err := json.Marshal(handleVpnnStatus())
	if err != nil {
		t.Fatal(err)
	}
	var status map[string]any
	if err := json.Unmarshal(data, &status); err != nil {
		t.Fatal(err)
	}
	value, present := status["captureReady"]
	if !present || value != false {
		t.Fatal("stopped capture was absent or reported ready")
	}
	if _, present := status["state"]; !present {
		t.Fatal("transport status was not preserved")
	}
}
