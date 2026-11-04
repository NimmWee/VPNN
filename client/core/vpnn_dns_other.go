//go:build !windows && !android

package core

func platformVpnnSystemDNS() []string { return nil }
