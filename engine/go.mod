module vpnn.local/engine

go 1.27.0

require (
	github.com/samosvalishe/free-turn-proxy v0.0.0
	masterdnsvpn-go v0.0.0
)

require (
	github.com/BurntSushi/toml v1.4.0 // indirect
	github.com/amnezia-vpn/amneziawg-go/v3 v3.1.20260814 // indirect
	github.com/andybalholm/brotli v1.2.2 // indirect
	github.com/bdandy/go-errors v1.2.2 // indirect
	github.com/bdandy/go-socks4 v1.2.3 // indirect
	github.com/bogdanfinn/fhttp v0.6.8 // indirect
	github.com/bogdanfinn/quic-go-utls v1.0.9-utls // indirect
	github.com/bogdanfinn/tls-client v1.15.1 // indirect
	github.com/bogdanfinn/utls v1.7.7-barnius // indirect
	github.com/bogdanfinn/websocket v1.5.5-barnius // indirect
	github.com/cbeuw/connutil v1.0.1 // indirect
	github.com/google/uuid v1.6.0 // indirect
	github.com/klauspost/compress v1.19.2 // indirect
	github.com/klauspost/cpuid/v2 v2.4.0 // indirect
	github.com/klauspost/reedsolomon v1.14.2 // indirect
	github.com/miekg/dns v1.1.73 // indirect
	github.com/pierrec/lz4/v4 v4.1.26 // indirect
	github.com/pion/dtls/v3 v3.1.5 // indirect
	github.com/pion/logging v0.2.4 // indirect
	github.com/pion/randutil v0.1.0 // indirect
	github.com/pion/stun/v3 v3.1.7 // indirect
	github.com/pion/transport/v4 v4.1.0 // indirect
	github.com/pion/turn/v5 v5.0.13 // indirect
	github.com/pkg/errors v0.9.1 // indirect
	github.com/quic-go/qpack v0.6.0 // indirect
	github.com/tam7t/hpkp v0.0.0-20160821193359-2b70b4024ed5 // indirect
	github.com/tjfoc/gmsm v1.4.1 // indirect
	github.com/wlynxg/anet v0.0.5 // indirect
	github.com/xtaci/kcp-go/v5 v5.6.72 // indirect
	github.com/xtaci/smux v1.5.57 // indirect
	golang.org/x/crypto v0.57.0 // indirect
	golang.org/x/crypto/x509roots/fallback v0.0.0-20260824205408-89f4e9bb5b38 // indirect
	golang.org/x/net v0.60.0 // indirect
	golang.org/x/sys v0.48.0 // indirect
	golang.org/x/text v0.42.0 // indirect
	golang.org/x/time v0.15.0 // indirect
	golang.zx2c4.com/wintun v0.0.0-20230126152724-0fa3db229ce2 // indirect
)

replace github.com/samosvalishe/free-turn-proxy => ../transports/freeturn

replace masterdnsvpn-go => ../transports/masterdns

replace github.com/wlynxg/anet => ../transports/anet
