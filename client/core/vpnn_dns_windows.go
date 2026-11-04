//go:build windows

package core

import (
	"net/netip"
	"runtime"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

func platformVpnnSystemDNS() []string {
	size := uint32(15000)
	for attempts := 0; attempts < 5 && size <= 1024*1024; attempts++ {
		buffer := make([]byte, size)
		first := (*windows.IpAdapterAddresses)(unsafe.Pointer(&buffer[0]))
		err := windows.GetAdaptersAddresses(syscall.AF_UNSPEC, windows.GAA_FLAG_INCLUDE_GATEWAYS, 0, first, &size)
		if err == syscall.ERROR_BUFFER_OVERFLOW {
			continue
		}
		if err != nil {
			return nil
		}
		result := []string{}
		for adapter := first; adapter != nil; adapter = adapter.Next {
			if adapter.OperStatus != windows.IfOperStatusUp || adapter.FirstGatewayAddress == nil {
				continue
			}
			for server := adapter.FirstDnsServerAddress; server != nil; server = server.Next {
				address, err := server.Address.Sockaddr.Sockaddr()
				if err != nil {
					continue
				}
				switch value := address.(type) {
				case *syscall.SockaddrInet4:
					result = append(result, netip.AddrFrom4(value.Addr).String())
				case *syscall.SockaddrInet6:
					result = append(result, netip.AddrFrom16(value.Addr).String())
				}
			}
		}
		runtime.KeepAlive(buffer)
		return result
	}
	return nil
}
