package vpnn

import "testing"

func TestDownloadMTUBoundsAndDefaults(t *testing.T) {
	for _, n := range []int{-1, 499, 1233} {
		if _, err := NewWithDownloadMTU([]string{"v.example.test"}, []string{"127.0.0.1:53"}, "0123456789abcdef0123456789abcdef", 5, 19082, t.TempDir(), nil, n); err == nil {
			t.Fatalf("accepted MTU %d", n)
		}
	}
	for _, n := range []int{0, 500, 1000, 1232} {
		if _, err := NewWithDownloadMTU([]string{"v.example.test"}, []string{"127.0.0.1:53"}, "0123456789abcdef0123456789abcdef", 5, 19082, t.TempDir(), nil, n); err != nil {
			t.Fatalf("MTU %d: %v", n, err)
		}
	}
}
