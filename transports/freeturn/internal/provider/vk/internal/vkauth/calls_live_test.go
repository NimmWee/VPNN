package vkauth

import (
	"context"
	"encoding/json"
	"net/url"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/samosvalishe/free-turn-proxy/internal/provider/vk/internal/personanet"
)

func TestVKCallsLive(t *testing.T) {
	filename := os.Getenv("VPNN_VK_CALLS_TEST_CONFIG")
	if filename == "" {
		t.Skip("set VPNN_VK_CALLS_TEST_CONFIG to a private engine configuration for one bounded VK Calls request chain")
	}
	data, err := os.ReadFile(filename)
	if err != nil {
		t.Fatal("cannot read private test configuration")
	}
	var config struct {
		VK struct {
			VK struct {
				Links []string `json:"links"`
			} `json:"vk"`
		} `json:"vk"`
	}
	if json.Unmarshal(data, &config) != nil || len(config.VK.VK.Links) == 0 {
		t.Fatal("missing private call link")
	}
	u, err := url.Parse(config.VK.VK.Links[0])
	if err != nil {
		t.Fatal("invalid private call link")
	}
	link := u.Path[strings.LastIndex(u.Path, "/")+1:]
	client := New(Config{ManualOnly: true})
	ctx, cancel := context.WithTimeout(context.Background(), 40*time.Second)
	defer cancel()
	username, password, addresses, err := client.getCallsTokenChain(ctx, link, personanet.NewCookieJar())
	if err != nil {
		t.Fatalf("native VK Calls flow: %v", err)
	}
	if username == "" || password == "" || len(addresses) == 0 {
		t.Fatal("incomplete TURN credentials")
	}
	t.Logf("VK Calls authorized without a CAPTCHA solver; relayCount=%d reusableSeconds=%d", len(addresses), int(time.Until(credentialExpiry(username, time.Now())).Seconds()))
}
