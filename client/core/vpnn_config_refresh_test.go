package core

import (
	"bufio"
	"fmt"
	"net"
	"testing"
	"time"

	"github.com/metacubex/mihomo/config"
	C "github.com/metacubex/mihomo/constant"
	"github.com/metacubex/mihomo/listener/inbound"
)

type refreshTestTunnel struct {
	C.Tunnel
	received chan *C.Metadata
}

func (t refreshTestTunnel) HandleTCPConn(conn net.Conn, metadata *C.Metadata) {
	defer conn.Close()
	t.received <- metadata
}

func TestVpnnRefreshListenerPinsProxy(t *testing.T) {
	raw := config.DefaultRawConfig()
	raw.Proxy = []map[string]any{{"name": "VPNN", "type": "socks5", "server": "127.0.0.1", "port": 19082}}
	raw.Rule = []string{"MATCH,DIRECT"}
	raw.Listeners = []map[string]any{{"name": "VPNN config refresh", "type": "http", "listen": "127.0.0.1", "port": 19094, "users": []any{}, "proxy": "VPNN"}}
	cfg, err := config.ParseRawConfig(raw)
	if err != nil {
		t.Fatal(err)
	}
	listener := cfg.Listeners["VPNN config refresh"]
	if listener == nil {
		t.Fatal("missing refresh listener")
	}
	option, ok := listener.Config().(*inbound.HTTPOption)
	if !ok || option.SpecialProxy != "VPNN" || option.Listen != "127.0.0.1" || option.Users == nil {
		t.Fatalf("refresh path not pinned: %+v", listener.Config())
	}
	local := *option
	local.Port = "0"
	proxy, err := inbound.NewHTTP(&local)
	if err != nil {
		t.Fatal(err)
	}
	received := make(chan *C.Metadata, 1)
	if err := proxy.Listen(refreshTestTunnel{received: received}); err != nil {
		t.Fatal(err)
	}
	defer proxy.Close()
	conn, err := net.DialTimeout("tcp", proxy.Address(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	conn.SetDeadline(time.Now().Add(2 * time.Second))
	fmt.Fprint(conn, "CONNECT unreachable.invalid:443 HTTP/1.1\r\nHost: unreachable.invalid:443\r\n\r\n")
	if _, err := bufio.NewReader(conn).ReadString('\n'); err != nil {
		t.Fatal(err)
	}
	select {
	case metadata := <-received:
		if metadata.SpecialProxy != "VPNN" || metadata.Host != "unreachable.invalid" {
			t.Fatalf("CONNECT escaped named outbound: %+v", metadata)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("refresh CONNECT did not reach Core tunnel")
	}
}
