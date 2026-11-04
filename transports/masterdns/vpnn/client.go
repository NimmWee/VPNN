// Package vpnn embeds the MIT-licensed MasterDnsVPN client without a second TUN.
package vpnn

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"

	"masterdnsvpn-go/internal/client"
	"masterdnsvpn-go/internal/config"
)

type Client struct{ client *client.Client }

func New(domains, resolvers []string, key string, encryption int, listenPort int, stateDir string, protect func(int) bool) (*Client, error) {
	return NewWithDownloadMTU(domains, resolvers, key, encryption, listenPort, stateDir, protect, 0)
}

func NewWithDownloadMTU(domains, resolvers []string, key string, encryption int, listenPort int, stateDir string, protect func(int) bool, maxDownloadMTU int) (*Client, error) {
	return NewForMeasurement(domains, resolvers, key, encryption, listenPort, stateDir, protect, maxDownloadMTU, 0)
}

func NewForMeasurement(domains, resolvers []string, key string, encryption int, listenPort int, stateDir string, protect func(int) bool, maxDownloadMTU, duplication int) (*Client, error) {
	if maxDownloadMTU != 0 && (maxDownloadMTU < 500 || maxDownloadMTU > 1232) {
		return nil, errors.New("DNS download MTU must be zero or between 500 and 1232")
	}
	if duplication < 0 || duplication > 2 {
		return nil, errors.New("DNS duplication must be zero, one or two")
	}
	if err := os.MkdirAll(stateDir, 0700); err != nil {
		return nil, err
	}
	path := filepath.Join(stateDir, "resolvers.txt")
	if err := os.WriteFile(path, []byte(strings.Join(resolvers, "\n")+"\n"), 0600); err != nil {
		return nil, err
	}
	if encryption == 0 {
		encryption = 5
	}
	values := map[string]any{
		"DOMAINS": domains, "ENCRYPTION_KEY": key, "DATA_ENCRYPTION_METHOD": encryption,
		"LISTEN_IP": "127.0.0.1", "LISTEN_PORT": listenPort, "PROTOCOL_TYPE": "SOCKS5",
		"SOCKS5_AUTH": false, "LOCAL_DNS_ENABLED": true, "LOCAL_DNS_IP": "127.0.0.1", "LOCAL_DNS_PORT": listenPort + 1, "LOG_LEVEL": "ERROR",
		"SAVE_MTU_SERVERS_TO_FILE": false, "LOCAL_DNS_CACHE_PERSIST_TO_FILE": false,
	}
	if maxDownloadMTU != 0 {
		values["MAX_DOWNLOAD_MTU"] = maxDownloadMTU
	}
	if duplication != 0 {
		values["PACKET_DUPLICATION_COUNT"] = duplication
	}
	data, err := json.Marshal(values)
	if err != nil {
		return nil, err
	}
	cfg, err := config.LoadClientConfigFromJSONBase64WithOverrides(base64.StdEncoding.EncodeToString(data), config.ClientConfigOverrides{ResolversFilePath: &path})
	if err != nil {
		return nil, err
	}
	c, err := client.BootstrapLoadedConfig(cfg, "")
	if err != nil {
		return nil, err
	}
	c.SetSocketProtector(protect)
	return &Client{client: c}, nil
}

func (c *Client) Run(ctx context.Context) error { return c.client.Run(ctx) }

func (c *Client) Diagnostics() map[string]uint64 { return c.client.Diagnostics() }
