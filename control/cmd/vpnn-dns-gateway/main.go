package main

import (
	"context"
	"flag"
	"log"
	"net"
	"os"
	"os/signal"
	"syscall"
	"time"

	"vpnn.local/control/dnsgateway"
)

func main() {
	listen := flag.String("listen", "127.0.0.1:5353", "UDP DNS listener")
	zone := flag.String("zone", "", "delegated DNS zone")
	nameserver := flag.String("nameserver", "", "authoritative NS for delegated-zone discovery")
	targets := flag.String("targets", "private/dns-targets.json", "atomic JSON mapping of device domains to loopback services")
	workers := flag.Int("workers", 16, "bounded forwarding worker count")
	flag.Parse()
	gateway := dnsgateway.New(*zone)
	if *nameserver != "" {
		if err := gateway.SetNameserver(*nameserver); err != nil {
			log.Fatal(err)
		}
	}
	if err := gateway.Load(*targets); err != nil {
		log.Fatal(err)
	}
	connection, err := net.ListenPacket("udp", *listen)
	if err != nil {
		log.Fatal(err)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if err := gateway.Load(*targets); err != nil {
					log.Print("DNS backend reload rejected; keeping the last valid table")
				}
			}
		}
	}()
	log.Printf("VPNN authoritative device gateway: %s", connection.LocalAddr())
	if err := gateway.Serve(ctx, connection, *workers); err != nil {
		log.Fatal(err)
	}
}
