package dnsgateway

import (
	"context"
	"net"
	"sync/atomic"
	"testing"
	"time"

	"github.com/miekg/dns"
)

func TestGatewayAnswersDelegatedAuthorityWithoutADeviceBackend(t *testing.T) {
	g := New("v.example.test")
	g.nameserver = "ns.example.test."
	for _, kind := range []uint16{dns.TypeNS, dns.TypeSOA} {
		q := new(dns.Msg)
		q.SetQuestion("v.example.test.", kind)
		raw, _ := q.Pack()
		var response dns.Msg
		if response.Unpack(g.Resolve(context.Background(), raw)) != nil || response.Rcode != dns.RcodeSuccess || !response.Authoritative || len(response.Answer) != 1 {
			t.Fatal("delegated zone authority was not served")
		}
	}
}

func TestGatewayRefusesOpenResolverAndPublicBackends(t *testing.T) {
	g := New("v.example.test")
	for _, table := range []map[string]string{{"device.v.example.test": "8.8.8.8:53"}, {"outside.example.test": "127.0.0.1:5300"}, {"device.v.example.test": "127.0.0.1:53"}} {
		if g.Replace(table) == nil {
			t.Fatal("unsafe backend table accepted")
		}
	}
	q := new(dns.Msg)
	q.SetQuestion("www.example.com.", dns.TypeA)
	raw, _ := q.Pack()
	response := g.Resolve(context.Background(), raw)
	var msg dns.Msg
	if err := msg.Unpack(response); err != nil {
		t.Fatal(err)
	}
	if msg.Rcode != dns.RcodeRefused {
		t.Fatal("gateway behaved as an open resolver")
	}
}

func TestGatewayForwardsOwnedDeviceAndStopsAfterRevocation(t *testing.T) {
	backend, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer backend.Close()
	var count atomic.Int32
	go func() {
		buffer := make([]byte, 4096)
		for {
			n, addr, err := backend.ReadFrom(buffer)
			if err != nil {
				return
			}
			count.Add(1)
			var q dns.Msg
			if q.Unpack(buffer[:n]) != nil {
				continue
			}
			reply := new(dns.Msg)
			reply.SetReply(&q)
			reply.Answer = []dns.RR{&dns.TXT{Hdr: dns.RR_Header{Name: q.Question[0].Name, Rrtype: dns.TypeTXT, Class: dns.ClassINET, Ttl: 0}, Txt: []string{"opaque-test-payload"}}}
			raw, _ := reply.Pack()
			backend.WriteTo(raw, addr)
		}
	}()
	g := New("v.example.test")
	if err := g.Replace(map[string]string{"device.v.example.test": backend.LocalAddr().String()}); err != nil {
		t.Fatal(err)
	}
	q := new(dns.Msg)
	q.SetQuestion("encoded.packet.device.v.example.test.", dns.TypeTXT)
	raw, _ := q.Pack()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	var response dns.Msg
	if err := response.Unpack(g.Resolve(ctx, raw)); err != nil {
		t.Fatal(err)
	}
	if response.Id != q.Id || len(response.Answer) != 1 {
		t.Fatal("device packet was not forwarded")
	}
	if err := g.Replace(map[string]string{}); err != nil {
		t.Fatal(err)
	}
	if err := response.Unpack(g.Resolve(ctx, raw)); err != nil {
		t.Fatal(err)
	}
	if response.Rcode != dns.RcodeRefused || count.Load() != 1 {
		t.Fatal("revoked device still reached its backend")
	}
}
