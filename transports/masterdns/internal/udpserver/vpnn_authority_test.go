package udpserver

import (
	"github.com/miekg/dns"
	"masterdnsvpn-go/internal/config"
	"testing"
)

func TestDelegatedApexHasAuthoritativeNSAndSOA(t *testing.T) {
	s := &Server{cfg: config.ServerConfig{Domain: []string{"v.example.test"}, AuthoritativeNS: "ns.example.test"}}
	for _, kind := range []uint16{dns.TypeNS, dns.TypeSOA, dns.TypeA} {
		q := new(dns.Msg)
		q.SetQuestion("v.example.test.", kind)
		raw, _ := q.Pack()
		var response dns.Msg
		if err := response.Unpack(s.authorityResponse(raw)); err != nil {
			t.Fatal(err)
		}
		if !response.Authoritative || response.RecursionAvailable || response.Rcode != dns.RcodeSuccess || response.Id != q.Id {
			t.Fatal("invalid authority response")
		}
		if kind == dns.TypeA {
			if len(response.Answer) != 0 || len(response.Ns) != 1 || response.Ns[0].Header().Rrtype != dns.TypeSOA {
				t.Fatal("negative apex response lacks SOA")
			}
		} else if len(response.Answer) != 1 || response.Answer[0].Header().Rrtype != kind {
			t.Fatal("missing apex record")
		}
	}
	for _, name := range []string{"encoded.packet.v.example.test.", "www.example.com."} {
		q := new(dns.Msg)
		q.SetQuestion(name, dns.TypeTXT)
		raw, _ := q.Pack()
		if s.authorityResponse(raw) != nil {
			t.Fatal("authority intercepted tunnel data or unrelated domain")
		}
	}
}
