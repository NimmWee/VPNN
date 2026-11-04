package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"time"

	"golang.org/x/net/proxy"
	"vpnn.local/engine"
	"vpnn.local/engine/measure"
)

func run() error {
	endpoint := flag.String("url", "", "bounded download endpoint (HTTPS; loopback HTTP only with -synthetic)")
	socks := flag.String("proxy", "", "explicit 127.0.0.1 SOCKS5 address; empty means direct")
	config := flag.String("engine-config", "", "optional private engine configuration; never printed")
	state := flag.String("state-dir", "", "private engine state directory")
	output := flag.String("output", "", "report JSON path")
	repeats := flag.Int("repeats", 3, "3..10 repeats")
	bytes := flag.Int64("bytes", 262144, "maximum bytes per transfer (up to 8 MiB)")
	parallel := flag.Int("parallel", 1, "1..4 concurrent transfers")
	upload := flag.Bool("upload", false, "POST bounded bytes to the explicitly selected upload endpoint")
	dnsMTU := flag.Int("dns-download-mtu", 0, "experimental DNS download limit, 500..1232; zero preserves defaults")
	dnsDup := flag.Int("dns-duplication", 0, "experimental DNS data duplication, 1..2; zero preserves defaults")
	timeout := flag.Duration("timeout", 20*time.Second, "per-transfer timeout, up to 60s")
	synthetic := flag.Bool("synthetic", false, "mark local/synthetic measurements")
	expected := flag.String("expect-ip", "", "require this IPv4/IPv6 from api.ipify.org through the same SOCKS")
	flag.Parse()
	if *output == "" {
		return errors.New("output is required")
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	ctx, deadline := context.WithTimeout(ctx, 12*time.Minute)
	defer deadline()
	var manager engine.Manager
	if *config != "" {
		data, err := os.ReadFile(*config)
		var cfg engine.Config
		if err != nil || len(data) > 256000 || json.Unmarshal(data, &cfg) != nil || cfg.Validate() != nil || *state == "" {
			return errors.New("invalid private engine configuration or missing state-dir")
		}
		if *socks == "" && cfg.Mode == "dns" {
			*socks = cfg.Listen
		}
		if *socks == "" {
			return errors.New("VK requires a separate explicit SOCKS client")
		}
		if err := manager.StartMeasurement(cfg, *state, nil, nil, *dnsMTU, *dnsDup); err != nil {
			return errors.New("engine startup failed")
		}
		defer manager.Stop()
		startup := time.NewTimer(95 * time.Second)
		defer startup.Stop()
		ticker := time.NewTicker(250 * time.Millisecond)
		defer ticker.Stop()
	waiting:
		for {
			switch manager.Status().State {
			case "ready", "connected":
				break waiting
			case "captcha":
				return errors.New("manual CAPTCHA required; no benchmark performed")
			case "error":
				return errors.New("transport failed before benchmark")
			}
			select {
			case <-ctx.Done():
				return errors.New("cancelled")
			case <-startup.C:
				return errors.New("transport startup deadline")
			case <-ticker.C:
			}
		}
	}
	verified := false
	if *expected != "" {
		if net.ParseIP(*expected) == nil || *socks == "" {
			return errors.New("expected IP requires a valid IP and explicit SOCKS")
		}
		d, err := proxy.SOCKS5("tcp", *socks, nil, &net.Dialer{Timeout: 10 * time.Second})
		if err != nil {
			return err
		}
		tr := &http.Transport{DialContext: d.(proxy.ContextDialer).DialContext}
		defer tr.CloseIdleConnections()
		c := &http.Client{Transport: tr, Timeout: 20 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
		req, _ := http.NewRequestWithContext(ctx, "GET", "https://api.ipify.org/", nil)
		resp, err := c.Do(req)
		if err != nil {
			return errors.New("egress verification unavailable")
		}
		body, err := io.ReadAll(io.LimitReader(resp.Body, 128))
		resp.Body.Close()
		if err != nil || resp.StatusCode != 200 || !net.ParseIP(string(body)).Equal(net.ParseIP(*expected)) {
			return errors.New("egress mismatch; benchmark refused")
		}
		verified = true
	}
	before := manager.Diagnostics()
	r, err := measure.Run(ctx, measure.Options{URL: *endpoint, Proxy: *socks, Repeats: *repeats, Bytes: *bytes, Timeout: *timeout, Parallel: *parallel, Synthetic: *synthetic, Upload: *upload})
	if err != nil {
		return err
	}
	r.EgressVerified = verified
	r.TransportBefore = before
	r.TransportAfter = manager.Diagnostics()
	data, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(*output, data, 0600); err != nil {
		return errors.New("cannot write report")
	}
	fmt.Printf("samples=%d successes=%d medianMbps=%.4f synthetic=%t egressVerified=%t\n", len(r.Samples), r.Successes, r.MedianMbps, r.Synthetic, r.EgressVerified)
	if r.Successes != len(r.Samples) {
		return errors.New("one or more transfers failed; see sanitized report")
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
