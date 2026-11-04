package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"vpnn.local/control"
)

func main() {
	listen := flag.String("listen", "127.0.0.1:8098", "HTTP listener; put HTTPS reverse proxy in front for remote use")
	state := flag.String("state", "private/control/state.json", "persistent state file")
	secretFile := flag.String("admin-secret-file", "private/control/admin.secret", "admin secret; generated if missing")
	allowRemote := flag.Bool("allow-remote", false, "explicitly allow a non-loopback HTTP listener")
	nodeStatus := flag.String("node-status-file", "", "local node reconciler status, visible to administrators only")
	maxDevices := flag.Int("max-active-devices", 8, "active device capacity of the single VPS")
	publicURL := flag.String("public-url", "", "public HTTPS origin bound into signed offline invitations")
	flag.Parse()
	host, _, err := net.SplitHostPort(*listen)
	if err != nil {
		log.Fatal("invalid listener")
	}
	if ip := net.ParseIP(host); !(*allowRemote) && (ip == nil || !ip.IsLoopback()) {
		log.Fatal("HTTP must bind to loopback unless -allow-remote is explicitly set")
	}
	secret, err := os.ReadFile(*secretFile)
	if errors.Is(err, os.ErrNotExist) {
		if err = os.MkdirAll(filepath.Dir(*secretFile), 0700); err != nil {
			log.Fatal(err)
		}
		b := make([]byte, 32)
		if _, err = rand.Read(b); err != nil {
			log.Fatal(err)
		}
		secret = []byte(base64.RawURLEncoding.EncodeToString(b))
		if err = os.WriteFile(*secretFile, secret, 0600); err != nil {
			log.Fatal(err)
		}
	} else if err != nil {
		log.Fatal(err)
	}
	app, err := control.Open(*state, strings.TrimSpace(string(secret)))
	if err != nil {
		log.Fatal(err)
	}
	app.NodeStatusPath = *nodeStatus
	app.MaxActiveDevices = *maxDevices
	if *publicURL != "" {
		origin, err := url.Parse(*publicURL)
		if err != nil || origin.Scheme != "https" || origin.Hostname() == "" || origin.User != nil || origin.RawQuery != "" || origin.Fragment != "" || (origin.Path != "" && origin.Path != "/") {
			log.Fatal("public-url must be a plain HTTPS origin")
		}
		app.PublicURL = strings.TrimSuffix(*publicURL, "/")
	}
	server := &http.Server{Addr: *listen, Handler: app.Handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16 * 1024}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	fmt.Printf("VPNN control: http://%s\nAdmin secret file: %s\nSigning public key: %s\n", *listen, *secretFile, app.PublicKey())
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
