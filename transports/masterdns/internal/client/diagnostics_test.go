package client

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestDiagnosticsAreNumericAndExcludeResolverIdentities(t *testing.T) {
	c := &Client{}
	c.perf.txPackets.Add(3)
	c.perf.txBytes.Add(123)
	c.perf.downloadMTU.Store(500)
	c.rxDroppedPackets.Add(2)
	got := c.Diagnostics()
	if got["dnsTxPackets"] != 3 || got["dnsTxBytes"] != 123 || got["dnsDownloadMTU"] != 500 || got["dnsRxDropped"] != 2 {
		t.Fatalf("bad counters: %+v", got)
	}
	data, _ := json.Marshal(got)
	if strings.Contains(string(data), "resolver") || strings.Contains(string(data), "key") {
		t.Fatal("identity leaked")
	}
}
