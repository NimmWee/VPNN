package client

import (
	"context"
	"net"
	"testing"
)

func TestEmbeddingProtectorRejectsUpstreamSocket(t *testing.T) {
	c := &Client{}
	c.SetSocketProtector(func(int) bool { return false })
	conn, err := c.listenUDPProtected(context.Background(), "127.0.0.1:0")
	if conn != nil {
		conn.Close()
	}
	if err == nil {
		t.Fatal("socket was opened after the host rejected protect")
	}
}

func TestEmbeddingProtectorRunsForResolverSocket(t *testing.T) {
	c := &Client{}
	calls := 0
	c.SetSocketProtector(func(int) bool { calls++; return true })
	listener, err := net.ListenPacket("udp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	conn, err := c.dialUDPResolver(context.Background(), listener.LocalAddr().String())
	if err != nil {
		t.Fatal(err)
	}
	conn.Close()
	if calls != 1 {
		t.Fatalf("protect calls = %d", calls)
	}
}
