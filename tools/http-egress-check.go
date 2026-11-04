package main

import (
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strings"
	"time"
)

func main() {
	blocked := flag.String("blocked-peer", "", "TCP peer which must be unreachable")
	expect := flag.String("expect-ip", "", "required tunnel egress IP")
	flag.Parse()
	if *blocked != "" {
		c, err := net.DialTimeout("tcp", *blocked, 3*time.Second)
		if err == nil {
			c.Close()
			fmt.Fprintln(os.Stderr, "direct VPS unexpectedly reachable")
			os.Exit(1)
		}
		fmt.Println("DIRECT_VPS_BLOCK_CONFIRMED")
	}
	client := &http.Client{Timeout: 60 * time.Second}
	response, err := client.Get("https://1.1.1.1/cdn-cgi/trace")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 8192))
	if err != nil || response.StatusCode != 200 {
		fmt.Fprintln(os.Stderr, "HTTPS failed")
		os.Exit(1)
	}
	for _, line := range strings.Split(string(body), "\n") {
		if strings.HasPrefix(line, "ip=") {
			if *expect != "" && line != "ip="+*expect {
				fmt.Fprintln(os.Stderr, "unexpected egress IP")
				os.Exit(1)
			}
			fmt.Println("HTTPS_OK", line)
			return
		}
	}
	fmt.Fprintln(os.Stderr, "egress IP not found")
	os.Exit(1)
}
