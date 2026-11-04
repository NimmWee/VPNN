package measure

import (
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
	"runtime"
	"slices"
	"strconv"
	"sync"
	"time"

	"golang.org/x/net/proxy"
)

type Options struct {
	Upload    bool
	URL       string
	Proxy     string
	Repeats   int
	Bytes     int64
	Timeout   time.Duration
	Parallel  int
	Synthetic bool
}

type Sample struct {
	Repeat      int     `json:"repeat"`
	Bytes       int64   `json:"bytes"`
	DurationMS  float64 `json:"durationMs"`
	ConnectMS   float64 `json:"connectMs"`
	FirstByteMS float64 `json:"firstByteMs"`
	Mbps        float64 `json:"mbps"`
	Error       string  `json:"error,omitempty"`
}

type Report struct {
	Direction            string            `json:"direction"`
	MedianAggregateMbps  float64           `json:"medianAggregateMbps"`
	TransportBefore      map[string]uint64 `json:"transportBefore,omitempty"`
	TransportAfter       map[string]uint64 `json:"transportAfter,omitempty"`
	Schema               int               `json:"schema"`
	Path                 string            `json:"path"`
	Synthetic            bool              `json:"synthetic"`
	Parallel             int               `json:"parallel"`
	ByteLimitPerTransfer int64             `json:"byteLimitPerTransfer"`
	Samples              []Sample          `json:"samples"`
	Successes            int               `json:"successes"`
	MedianMbps           float64           `json:"medianMbps"`
	MinMbps              float64           `json:"minMbps"`
	MaxMbps              float64           `json:"maxMbps"`
	FirstByteP50MS       float64           `json:"firstByteP50Ms"`
	FirstByteP95MS       float64           `json:"firstByteP95Ms"`
	HeapBefore           uint64            `json:"heapBefore"`
	HeapAfter            uint64            `json:"heapAfter"`
	EgressVerified       bool              `json:"egressVerified"`
}

func Run(ctx context.Context, o Options) (Report, error) {
	u, err := url.Parse(o.URL)
	if err != nil || u.Hostname() == "" || u.User != nil || (u.Scheme != "https" && !(o.Synthetic && u.Scheme == "http" && net.ParseIP(u.Hostname()).IsLoopback())) {
		return Report{}, errors.New("HTTPS required; synthetic HTTP must use loopback without credentials")
	}
	if o.Repeats < 3 || o.Repeats > 10 || o.Bytes < 1 || o.Bytes > 8<<20 || o.Parallel < 1 || o.Parallel > 4 || o.Timeout < time.Millisecond || o.Timeout > 60*time.Second {
		return Report{}, errors.New("limits: 3..10 repeats, 1..8388608 bytes, 1..4 parallel, 1ms..60s per transfer")
	}
	dial := (&net.Dialer{Timeout: o.Timeout}).DialContext
	path := "direct"
	if o.Proxy != "" {
		host, _, err := net.SplitHostPort(o.Proxy)
		if err != nil || host != "127.0.0.1" {
			return Report{}, errors.New("SOCKS must listen on 127.0.0.1")
		}
		d, err := proxy.SOCKS5("tcp", o.Proxy, nil, &net.Dialer{Timeout: o.Timeout})
		if err != nil {
			return Report{}, errors.New("invalid SOCKS proxy")
		}
		dial = d.(proxy.ContextDialer).DialContext
		path = "explicit-socks"
	}
	transport := &http.Transport{DialContext: dial, DisableCompression: true, DisableKeepAlives: true, MaxResponseHeaderBytes: 16384}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	r := Report{Schema: 1, Path: path, Synthetic: o.Synthetic, Parallel: o.Parallel, ByteLimitPerTransfer: o.Bytes}
	r.Direction = "download"
	if o.Upload {
		r.Direction = "upload"
	}
	var aggregate []float64
	var mem runtime.MemStats
	runtime.ReadMemStats(&mem)
	r.HeapBefore = mem.HeapAlloc
	for repeat := 1; repeat <= o.Repeats; repeat++ {
		if ctx.Err() != nil {
			return r, ctx.Err()
		}
		samples := make([]Sample, o.Parallel)
		roundStart := time.Now()
		var wg sync.WaitGroup
		for i := range samples {
			wg.Add(1)
			go func(i int) { defer wg.Done(); samples[i] = transfer(ctx, client, o, repeat) }(i)
		}
		wg.Wait()
		var total int64
		complete := true
		for _, sample := range samples {
			total += sample.Bytes
			if sample.Error != "" {
				complete = false
			}
		}
		if complete {
			aggregate = append(aggregate, float64(total)*8/max(time.Since(roundStart).Seconds(), .000001)/1e6)
		}
		r.Samples = append(r.Samples, samples...)
	}
	runtime.ReadMemStats(&mem)
	r.HeapAfter = mem.HeapAlloc
	var speeds, first []float64
	for _, s := range r.Samples {
		if s.Error == "" {
			r.Successes++
			speeds = append(speeds, s.Mbps)
			first = append(first, s.FirstByteMS)
		}
	}
	if len(speeds) > 0 {
		slices.Sort(speeds)
		slices.Sort(first)
		r.MedianMbps = percentile(speeds, .5)
		r.MinMbps = speeds[0]
		r.MaxMbps = speeds[len(speeds)-1]
		r.FirstByteP50MS = percentile(first, .5)
		r.FirstByteP95MS = percentile(first, .95)
	}
	if len(aggregate) > 0 {
		slices.Sort(aggregate)
		r.MedianAggregateMbps = percentile(aggregate, .5)
	}
	return r, nil
}

func percentile(values []float64, p float64) float64 {
	pos := p * float64(len(values)-1)
	lo := int(pos)
	hi := lo + 1
	if hi >= len(values) {
		return values[lo]
	}
	return values[lo] + (values[hi]-values[lo])*(pos-float64(lo))
}

func transfer(parent context.Context, client *http.Client, o Options, repeat int) Sample {
	ctx, cancel := context.WithTimeout(parent, o.Timeout)
	defer cancel()
	s := Sample{Repeat: repeat}
	start := time.Now()
	var mu sync.Mutex
	trace := &httptrace.ClientTrace{GotConn: func(httptrace.GotConnInfo) {
		mu.Lock()
		s.ConnectMS = float64(time.Since(start).Microseconds()) / 1000
		mu.Unlock()
	}, GotFirstResponseByte: func() { mu.Lock(); s.FirstByteMS = float64(time.Since(start).Microseconds()) / 1000; mu.Unlock() }}
	method := "GET"
	var body io.Reader
	if o.Upload {
		method = "POST"
		body = io.LimitReader(zeroReader{}, o.Bytes)
	}
	req, _ := http.NewRequestWithContext(httptrace.WithClientTrace(ctx, trace), method, o.URL, body)
	if o.Upload {
		req.ContentLength = o.Bytes
		req.Header.Set("Content-Type", "application/octet-stream")
	}
	req.Header.Set("Cache-Control", "no-cache")
	req.Header.Set("Range", "bytes=0-"+strconv.FormatInt(o.Bytes-1, 10))
	resp, err := client.Do(req)
	if err == nil {
		if resp.StatusCode != 200 && resp.StatusCode != 206 {
			s.Error = "http-status"
		} else {
			if o.Upload {
				_, err = io.Copy(io.Discard, io.LimitReader(resp.Body, 4096))
				if err == nil {
					s.Bytes = o.Bytes
				}
			} else {
				s.Bytes, err = io.Copy(io.Discard, io.LimitReader(resp.Body, o.Bytes))
			}
		}
		resp.Body.Close()
	}
	mu.Lock()
	defer mu.Unlock()
	s.DurationMS = max(float64(time.Since(start).Nanoseconds())/1e6, 0.001)
	if err != nil {
		if ctx.Err() != nil {
			s.Error = "deadline-or-cancelled"
		} else {
			s.Error = "transport"
		}
	}
	if s.Error == "" && s.Bytes != o.Bytes {
		s.Error = "short-body"
	}
	if s.Error == "" && s.DurationMS > 0 {
		s.Mbps = float64(s.Bytes) * 8 / (s.DurationMS * 1000)
	}
	return s
}

type zeroReader struct{}

func (zeroReader) Read(p []byte) (int, error) { clear(p); return len(p), nil }
