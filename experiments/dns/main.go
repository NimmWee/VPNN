package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"

	"masterdnsvpn-go/vpnn"
)

func main() {
	port := flag.Int("port", 0, "loopback SOCKS port; next UDP port is local DNS")
	resolver := flag.String("resolver", "", "lab resolver address")
	domain := flag.String("domain", "lab.example.test", "test domain")
	flag.Parse()
	if *port < 1025 || *port >= 65535 {
		log.Fatal("use a high loopback SOCKS port with a free successor")
	}
	key, err := os.ReadFile("lab.key")
	if err != nil {
		log.Fatal(err)
	}
	client, err := vpnn.New([]string{*domain}, []string{*resolver}, string(key), 5, *port, "state", nil)
	if err != nil {
		log.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		if err := client.Run(ctx); err != nil && ctx.Err() == nil {
			log.Fatal(err)
		}
	}()
	input := bufio.NewScanner(os.Stdin)
	for input.Scan() {
		data, err := json.Marshal(client.Diagnostics())
		if err != nil {
			log.Fatal(err)
		}
		fmt.Printf("LAB %s\n", data)
	}
}
