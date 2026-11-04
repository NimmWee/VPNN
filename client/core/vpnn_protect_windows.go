//go:build windows

package core

import (
	"errors"
	"net/netip"
	"unsafe"

	"github.com/metacubex/mihomo/component/dialer"
	"golang.org/x/sys/windows"
)

type vpnnRawSocket uintptr

func (s vpnnRawSocket) Control(f func(uintptr)) error  { f(uintptr(s)); return nil }
func (s vpnnRawSocket) Read(func(uintptr) bool) error  { return errors.New("control-only socket") }
func (s vpnnRawSocket) Write(func(uintptr) bool) error { return errors.New("control-only socket") }

func vpnnProtectFD(fd int) bool {
	if vpnnRequiresBind.Load() && dialer.DefaultInterface.Load() == "" && dialer.DefaultInterfaceFinder.Load() == nil {
		return false
	}
	// Control runs before bind/connect; getsockname rejects unbound Windows sockets.
	var info windows.WSAProtocolInfo
	size := int32(unsafe.Sizeof(info))
	const soProtocolInfoW = 0x2005
	if err := windows.Getsockopt(windows.Handle(fd), windows.SOL_SOCKET, soProtocolInfoW, (*byte)(unsafe.Pointer(&info)), &size); err != nil {
		return false
	}
	network, destination, target := "udp4", netip.MustParseAddr("1.1.1.1"), "1.1.1.1:53"
	switch info.AddressFamily {
	case windows.AF_INET:
	case windows.AF_INET6:
		network = "udp6"
		destination = netip.MustParseAddr("2606:4700:4700::1111")
		target = "[2606:4700:4700::1111]:53"
	default:
		return false
	}
	return dialer.ICMPControl(destination)(network, target, vpnnRawSocket(fd)) == nil
}
