// Explicit local-proxy diagnostics; this command never configures TUN, routes or system DNS.
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
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"time"

	"golang.org/x/net/proxy"
	"vpnn.local/engine"
)

func run() error {
	configFile := flag.String("config", "", "private engine JSON configuration")
	statusFile := flag.String("status-file", "", "private status including manual CAPTCHA URL")
	stateDir := flag.String("state-dir", "", "private transport state directory")
	probeProxy := flag.String("probe-proxy", "", "explicit local SOCKS5 proxy (DNS defaults to its own listener)")
	probeURL := flag.String("probe-url", "https://api.ipify.org/", "HTTPS reachability/egress check")
	timeout := flag.Duration("timeout", 3*time.Minute, "maximum wait for connection and HTTPS")
	flag.Parse()
	if *configFile == "" || *stateDir == "" || *statusFile == "" {
		return errors.New("config, state-dir and status-file are required")
	}
	data, err := os.ReadFile(*configFile)
	if err != nil {
		return errors.New("cannot read private configuration")
	}
	var cfg engine.Config
	if len(data) > 256000 || json.Unmarshal(data, &cfg) != nil {
		return errors.New("invalid private configuration")
	}
	if err := cfg.Validate(); err != nil {
		return err
	}
	if *probeProxy == "" && cfg.Mode == "dns" {
		*probeProxy = cfg.Listen
	}
	host, _, err := net.SplitHostPort(*probeProxy)
	if err != nil || host != "127.0.0.1" {
		return errors.New("probe requires a 127.0.0.1 SOCKS proxy")
	}
	u, err := url.Parse(*probeURL)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" {
		return errors.New("probe URL must use HTTPS")
	}
	if err := os.MkdirAll(*stateDir, 0700); err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(*statusFile), 0700); err != nil {
		return err
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()
	ctx, deadline := context.WithTimeout(ctx, *timeout)
	defer deadline()
	var manager engine.Manager
	if err := manager.Start(cfg, *stateDir, nil, nil); err != nil {
		return errors.New("transport startup failed")
	}
	defer manager.Stop()
	last := ""
	for ctx.Err() == nil {
		status := manager.Status()
		if status.State != last {
			last = status.State
			fmt.Printf("transport=%s state=%s streams=%d\n", cfg.Mode, status.State, status.Streams)
		}
		statusData, _ := json.Marshal(status)
		if err := os.WriteFile(*statusFile+".tmp", statusData, 0600); err != nil {
			return err
		}
		if err := os.Rename(*statusFile+".tmp", *statusFile); err != nil {
			return err
		}
		if status.State == "connected" || status.State == "ready" {
			if err := probe(ctx, *probeProxy, *probeURL); err == nil {
				return nil
			}
		}
		select {
		case <-ctx.Done():
		case <-time.After(time.Second):
		}
	}
	return errors.New("HTTPS through transport was not confirmed before timeout; inspect private status for manual CAPTCHA")
}

func probe(ctx context.Context, address, endpoint string) error {
	dialer, err := proxy.SOCKS5("tcp", address, nil, &net.Dialer{Timeout: 5 * time.Second})
	if err != nil {
		return err
	}
	transport := &http.Transport{DialContext: dialer.(proxy.ContextDialer).DialContext}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 30 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return err
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 4096))
	if err != nil || response.StatusCode != 200 {
		return errors.New("HTTPS probe rejected")
	}
	if endpoint == "https://api.ipify.org/" {
		if net.ParseIP(string(body)) == nil {
			return errors.New("egress service returned invalid IP")
		}
		fmt.Printf("HTTPS_OK egress=%s\n", body)
	} else {
		fmt.Printf("HTTPS_OK status=%d bytes=%d\n", response.StatusCode, len(body))
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
