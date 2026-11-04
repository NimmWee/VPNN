package kcpmux

import (
	"fmt"
	"os"
	"sync"
	"testing"
	"time"
)

func TestSyntheticKCPMeasurementMatrix(t *testing.T) {
	if os.Getenv("VPNN_SYNTHETIC_BENCH") != "1" {
		t.Skip("set VPNN_SYNTHETIC_BENCH=1 for bounded in-memory KCP measurements; no TURN or operator network")
	}
	for _, sessions := range []int{1, 3, 6, 12} {
		for repeat := 1; repeat <= 3; repeat++ {
			t.Run(fmt.Sprintf("sessions%d/repeat%d", sessions, repeat), func(t *testing.T) {
				started := time.Now()
				var wg sync.WaitGroup
				for range sessions {
					wg.Add(1)
					go func() { defer wg.Done(); runRoundTrip(t, 0) }()
				}
				wg.Wait()
				elapsed := time.Since(started).Seconds()
				t.Logf("synthetic=true sessions=%d bytesPerSession=262144 aggregateMbps=%.3f elapsedMs=%.3f", sessions, float64(sessions*262144)*8/elapsed/1e6, elapsed*1000)
			})
		}
	}
}
