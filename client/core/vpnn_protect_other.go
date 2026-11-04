//go:build !android && !windows

package core

func vpnnProtectFD(int) bool { return !vpnnRequiresBind.Load() }
