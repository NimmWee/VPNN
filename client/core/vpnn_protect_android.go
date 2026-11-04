//go:build android

package core

func vpnnProtectFD(fd int) bool {
	th := activeTunHandler.Load()
	if th == nil {
		return true
	}
	th.mu.RLock()
	defer th.mu.RUnlock()
	return th.callbacks != nil && th.callbacks.Protect(fd)
}
