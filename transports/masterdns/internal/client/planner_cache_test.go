package client

import (
	"bytes"
	"testing"

	Enums "masterdnsvpn-go/internal/enums"
	VpnProto "masterdnsvpn-go/internal/vpnproto"
)

func TestPlannerReusesDomainEncodingWithoutReusingPacketPayload(t *testing.T) {
	c := createTestClient(t)
	conns := []Connection{{Domain: "example.com", Resolver: "127.0.0.1", ResolverPort: 53, Key: "local"}}
	domains := make(map[string]preparedTunnelDomain)
	packets := make(map[string][]byte)
	task := plannerTask{opts: VpnProto.BuildOptions{PacketType: Enums.PACKET_STREAM_DATA, StreamID: 1, Payload: []byte("first")}}
	frames, err := c.buildPlannedOutboundFrames(task, conns, "example.com", packets, domains, nil)
	if err != nil || len(frames) != 1 {
		t.Fatalf("first frame: %v", err)
	}
	oldPacket := append([]byte(nil), frames[0].packet...)
	oldQName := domains["example.com"].qname
	task.opts.Payload = []byte("second")
	frames, err = c.buildPlannedOutboundFrames(task, conns, "example.com", packets, domains, frames)
	if err != nil || len(frames) != 1 {
		t.Fatalf("second frame: %v", err)
	}
	if &domains["example.com"].qname[0] != &oldQName[0] {
		t.Fatal("domain is encoded and allocated again for each packet")
	}
	if bytes.Equal(oldPacket, frames[0].packet) {
		t.Fatal("previous packet payload reused")
	}
}

func BenchmarkPlannerDomainCache(b *testing.B) {
	for _, reuse := range []bool{false, true} {
		name := "uncached"
		if reuse {
			name = "retained"
		}
		b.Run(name, func(b *testing.B) {
			c := createTestClient(b)
			conns := []Connection{{Domain: "example.com", Resolver: "127.0.0.1", ResolverPort: 53, Key: "local"}}
			task := plannerTask{opts: VpnProto.BuildOptions{PacketType: Enums.PACKET_STREAM_DATA, StreamID: 1, Payload: make([]byte, 98)}}
			var domains map[string]preparedTunnelDomain
			var packets map[string][]byte
			if reuse {
				domains = make(map[string]preparedTunnelDomain)
				packets = make(map[string][]byte)
			}
			var frames []encodedOutboundDatagram
			b.ReportAllocs()
			b.ResetTimer()
			for b.Loop() {
				var err error
				frames, err = c.buildPlannedOutboundFrames(task, conns, "example.com", packets, domains, frames)
				if err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
