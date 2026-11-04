package measure

import (
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestBoundedTransferAndSummary(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, strings.Repeat("x", 4096)) }))
	defer s.Close()
	report, err := Run(context.Background(), Options{URL: s.URL, Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1, Synthetic: true})
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Samples) != 3 || report.Successes != 3 || report.MedianMbps <= 0 {
		t.Fatalf("invalid report: %+v", report)
	}
	for _, s := range report.Samples {
		if s.Bytes != 1024 || s.Error != "" {
			t.Fatalf("unbounded sample: %+v", s)
		}
	}
}

func TestProxyFailureNeverFallsBackToDirect(t *testing.T) {
	calls := 0
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls++ }))
	defer s.Close()
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	address := ln.Addr().String()
	ln.Close()
	report, err := Run(context.Background(), Options{URL: s.URL, Proxy: address, Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1, Synthetic: true})
	if err != nil {
		t.Fatal(err)
	}
	if report.Successes != 0 || calls != 0 {
		t.Fatalf("direct fallback: %+v calls=%d", report, calls)
	}
}

func TestValidationAndDeadline(t *testing.T) {
	for _, o := range []Options{{URL: "http://example.com", Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1}, {URL: "https://example.com", Proxy: "example.com:1080", Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1}, {URL: "https://user:secret@example.com", Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1}} {
		if _, err := Run(context.Background(), o); err == nil {
			t.Fatalf("accepted unsafe options: %+v", o)
		}
	}
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }))
	defer s.Close()
	start := time.Now()
	report, err := Run(context.Background(), Options{URL: s.URL, Repeats: 3, Bytes: 1024, Timeout: 30 * time.Millisecond, Parallel: 1, Synthetic: true})
	if err != nil || report.Successes != 0 || time.Since(start) > time.Second {
		t.Fatalf("deadline failed: %+v %v", report, err)
	}
}

func TestShortBodyIsNotSuccessfulSpeedMeasurement(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, "short") }))
	defer s.Close()
	report, err := Run(context.Background(), Options{URL: s.URL, Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1, Synthetic: true})
	if err != nil || report.Successes != 0 {
		t.Fatalf("short response accepted: %+v %v", report, err)
	}
}

func TestBoundedUpload(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n, _ := io.Copy(io.Discard, r.Body)
		if r.Method != "POST" || n != 1024 {
			t.Errorf("unexpected upload method=%s bytes=%d", r.Method, n)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer s.Close()
	report, err := Run(context.Background(), Options{URL: s.URL, Repeats: 3, Bytes: 1024, Timeout: time.Second, Parallel: 1, Synthetic: true, Upload: true})
	if err != nil || report.Successes != 3 {
		t.Fatalf("upload: %+v %v", report, err)
	}
}
