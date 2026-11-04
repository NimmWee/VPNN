package client

import "sync/atomic"

type performanceCounters struct {
	txPackets   atomic.Uint64
	rxPackets   atomic.Uint64
	txBytes     atomic.Uint64
	rxBytes     atomic.Uint64
	resends     atomic.Uint64
	writeErrors atomic.Uint64
	uploadMTU   atomic.Uint64
	downloadMTU atomic.Uint64
	window      atomic.Uint64
	duplication atomic.Uint64
}

func (c *Client) Diagnostics() map[string]uint64 {
	return map[string]uint64{
		"dnsTxPackets": c.perf.txPackets.Load(), "dnsRxPackets": c.perf.rxPackets.Load(),
		"dnsTxBytes": c.perf.txBytes.Load(), "dnsRxBytes": c.perf.rxBytes.Load(),
		"dnsResends": c.perf.resends.Load(), "dnsWriteErrors": c.perf.writeErrors.Load(),
		"dnsRxDropped": c.rxDroppedPackets.Load(), "dnsUploadMTU": c.perf.uploadMTU.Load(),
		"dnsDownloadMTU": c.perf.downloadMTU.Load(), "dnsWindow": c.perf.window.Load(),
		"dnsDuplication": c.perf.duplication.Load(),
	}
}

func (c *Client) recordNegotiatedPerformance() {
	c.perf.uploadMTU.Store(uint64(max(0, c.syncedUploadMTU)))
	c.perf.downloadMTU.Store(uint64(max(0, c.syncedDownloadMTU)))
	c.perf.window.Store(uint64(max(0, c.cfg.ARQWindowSize)))
	c.perf.duplication.Store(uint64(max(0, c.cfg.PacketDuplicationCount)))
}
