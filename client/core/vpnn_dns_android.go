//go:build android

package core

func platformVpnnSystemDNS() []string {
	if value := vpnnAndroidDNS.Load(); value != nil {
		return append([]string(nil), (*value)...)
	}
	return nil
}
