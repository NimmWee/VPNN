package udpserver

import (
	"strings"

	"github.com/miekg/dns"
)

func (s *Server) authorityResponse(packet []byte) []byte {
	if s.cfg.AuthoritativeNS == "" {
		return nil
	}
	var question dns.Msg
	if question.Unpack(packet) != nil || question.Response || question.Opcode != dns.OpcodeQuery || len(question.Question) != 1 || question.Question[0].Qclass != dns.ClassINET {
		return nil
	}
	name := dns.Fqdn(strings.ToLower(question.Question[0].Name))
	owned := false
	for _, domain := range s.cfg.Domain {
		if name == dns.Fqdn(strings.ToLower(domain)) {
			owned = true
			break
		}
	}
	if !owned {
		return nil
	}
	nameserver := dns.Fqdn(s.cfg.AuthoritativeNS)
	if _, ok := dns.IsDomainName(nameserver); !ok {
		return nil
	}
	response := new(dns.Msg)
	response.SetReply(&question)
	response.Authoritative = true
	response.RecursionAvailable = false
	soa := &dns.SOA{Hdr: dns.RR_Header{Name: name, Rrtype: dns.TypeSOA, Class: dns.ClassINET, Ttl: 300}, Ns: nameserver, Mbox: "hostmaster." + name, Serial: 1, Refresh: 3600, Retry: 300, Expire: 604800, Minttl: 60}
	switch question.Question[0].Qtype {
	case dns.TypeNS:
		response.Answer = []dns.RR{&dns.NS{Hdr: dns.RR_Header{Name: name, Rrtype: dns.TypeNS, Class: dns.ClassINET, Ttl: 300}, Ns: nameserver}}
	case dns.TypeSOA:
		response.Answer = []dns.RR{soa}
	default:
		response.Ns = []dns.RR{soa}
	}
	data, err := response.Pack()
	if err != nil {
		return nil
	}
	return data
}
