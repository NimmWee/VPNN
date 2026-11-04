//go:build windows

package core

import (
	"context"
	"errors"
	"net"
	"syscall"
	"testing"

	"github.com/metacubex/mihomo/component/dialer"
)

func TestVpnnProtectUnboundWindowsSocket(t *testing.T) {
	previousBind := vpnnRequiresBind.Swap(false)
	previousInterface := dialer.DefaultInterface.Load()
	previousFinder := dialer.DefaultInterfaceFinder.Load()
	previousHook := dialer.DefaultSocketHook
	dialer.DefaultInterface.Store("")
	dialer.DefaultInterfaceFinder.Store(nil)
	dialer.DefaultSocketHook = nil
	t.Cleanup(func() {
		vpnnRequiresBind.Store(previousBind)
		dialer.DefaultInterface.Store(previousInterface)
		dialer.DefaultInterfaceFinder.Store(previousFinder)
		dialer.DefaultSocketHook = previousHook
	})
	for _, address := range []string{"127.0.0.1:0", "[::1]:0"} {
		t.Run(address, func(t *testing.T) {
			checked := false
			lc := net.ListenConfig{Control: func(_, _ string, socket syscall.RawConn) error {
				accepted := false
				if err := socket.Control(func(fd uintptr) {
					checked = true
					accepted = vpnnProtectFD(int(fd))
				}); err != nil {
					return err
				}
				if !accepted {
					return errors.New("host refused an unbound Windows socket")
				}
				return nil
			}}
			conn, err := lc.ListenPacket(context.Background(), "udp", address)
			if err != nil {
				if !checked {
					t.Skipf("address family unavailable: %v", err)
				}
				t.Fatal(err)
			}
			conn.Close()
		})
	}
}
