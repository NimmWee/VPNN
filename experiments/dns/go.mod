module vpnn.local/dnslab

go 1.27.0

require masterdnsvpn-go v0.0.0

require (
	github.com/BurntSushi/toml v1.4.0 // indirect
	github.com/klauspost/compress v1.18.5 // indirect
	github.com/pierrec/lz4/v4 v4.1.26 // indirect
	golang.org/x/crypto v0.54.0 // indirect
	golang.org/x/sys v0.47.0 // indirect
)

replace masterdnsvpn-go => ../../transports/masterdns
