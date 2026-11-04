package dnsgateway

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/netip"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/miekg/dns"
)

type Gateway struct {
	zone       string
	nameserver string
	targets    atomic.Value
}

func New(zone string) *Gateway {
	g := &Gateway{zone: strings.ToLower(strings.TrimSuffix(zone, "."))}
	g.targets.Store(map[string]string{})
	return g
}

func (g *Gateway) SetNameserver(name string) error {
	if _, ok := dns.IsDomainName(name); !ok || !strings.Contains(strings.TrimSuffix(name, "."), ".") {
		return errors.New("invalid authoritative nameserver")
	}
	g.nameserver = dns.Fqdn(name)
	return nil
}

func (g *Gateway) Replace(table map[string]string) error {
	if _, ok := dns.IsDomainName(g.zone); !ok || !strings.Contains(g.zone, ".") {
		return errors.New("invalid delegated zone")
	}
	if len(table) > 200 {
		return errors.New("too many DNS backends")
	}
	copy := make(map[string]string, len(table))
	for name, target := range table {
		name = strings.ToLower(strings.TrimSuffix(name, "."))
		if _, ok := dns.IsDomainName(name); !ok || !strings.HasSuffix(name, "."+g.zone) {
			return errors.New("backend must belong to the delegated zone")
		}
		address, err := netip.ParseAddrPort(target)
		if err != nil || !address.Addr().IsLoopback() || address.Port() < 1024 {
			return errors.New("backend must be a private loopback service, not a recursive resolver")
		}
		copy[name] = address.String()
	}
	g.targets.Store(copy)
	return nil
}

func (g *Gateway) Load(path string) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if len(b) > 64000 {
		return errors.New("backend table is too large")
	}
	var table map[string]string
	if err := json.Unmarshal(b, &table); err != nil {
		return err
	}
	return g.Replace(table)
}

func reply(question *dns.Msg, rcode int) []byte {
	m := new(dns.Msg)
	m.SetRcode(question, rcode)
	m.Authoritative = true
	m.RecursionAvailable = false
	b, _ := m.Pack()
	return b
}

func (g *Gateway) Resolve(ctx context.Context, raw []byte) []byte {
	if len(raw) > 4096 {
		return nil
	}
	var question dns.Msg
	if question.Unpack(raw) != nil || question.Response || len(question.Question) != 1 || question.Opcode != dns.OpcodeQuery {
		return nil
	}
	name := strings.ToLower(strings.TrimSuffix(question.Question[0].Name, "."))
	if name == g.zone && g.nameserver != "" && question.Question[0].Qclass == dns.ClassINET {
		answer := new(dns.Msg)
		answer.SetReply(&question)
		answer.Authoritative = true
		header := dns.RR_Header{Name: dns.Fqdn(g.zone), Class: dns.ClassINET, Ttl: 60}
		switch question.Question[0].Qtype {
		case dns.TypeNS:
			header.Rrtype = dns.TypeNS
			answer.Answer = []dns.RR{&dns.NS{Hdr: header, Ns: g.nameserver}}
		case dns.TypeSOA:
			header.Rrtype = dns.TypeSOA
			answer.Answer = []dns.RR{&dns.SOA{Hdr: header, Ns: g.nameserver, Mbox: "hostmaster." + dns.Fqdn(g.zone), Serial: 1, Refresh: 3600, Retry: 600, Expire: 86400, Minttl: 30}}
		}
		if len(answer.Answer) > 0 {
			data, _ := answer.Pack()
			return data
		}
	}
	best, target := "", ""
	for domain, address := range g.targets.Load().(map[string]string) {
		if (name == domain || strings.HasSuffix(name, "."+domain)) && len(domain) > len(best) {
			best, target = domain, address
		}
	}
	if target == "" {
		return reply(&question, dns.RcodeRefused)
	}
	connection, err := (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, "udp", target)
	if err != nil {
		return reply(&question, dns.RcodeServerFailure)
	}
	defer connection.Close()
	deadline := time.Now().Add(2 * time.Second)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	connection.SetDeadline(deadline)
	if _, err := connection.Write(raw); err != nil {
		return reply(&question, dns.RcodeServerFailure)
	}
	buffer := make([]byte, 4096)
	n, err := connection.Read(buffer)
	if err != nil || n < 12 || !bytes.Equal(buffer[:2], raw[:2]) || buffer[2]&0x80 == 0 {
		return reply(&question, dns.RcodeServerFailure)
	}
	return buffer[:n]
}

// Serve owns the supplied socket and closes it when the context ends.
func (g *Gateway) Serve(parent context.Context, connection net.PacketConn, workers int) error {
	if workers < 1 || workers > 64 {
		return errors.New("worker count must be between 1 and 64")
	}
	ctx, cancel := context.WithCancel(parent)
	defer cancel()
	defer connection.Close()
	type job struct {
		data    []byte
		address net.Addr
	}
	jobs := make(chan job, 256)
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range jobs {
				if ctx.Err() != nil {
					continue
				}
				response := g.Resolve(ctx, item.data)
				if len(response) > 0 {
					connection.WriteTo(response, item.address)
				}
			}
		}()
	}
	go func() { <-ctx.Done(); connection.Close() }()
	defer func() { cancel(); close(jobs); wg.Wait() }()
	buffer := make([]byte, 4097)
	for {
		n, address, err := connection.ReadFrom(buffer)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		if n > 4096 {
			continue
		}
		data := append([]byte(nil), buffer[:n]...)
		select {
		case jobs <- job{data, address}:
		default:
		}
	}
}
