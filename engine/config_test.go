package engine

import (
	"encoding/json"
	"fmt"
	"testing"
)

func TestValidateRejectsPublicListenerAndUnknownMode(t *testing.T) {
	for _, raw := range []string{
		`{"mode":"vk","listen":"0.0.0.0:19081","vk":{}}`,
		`{"mode":"shell","listen":"127.0.0.1:19081"}`,
		`{"mode":"dns","listen":"127.0.0.1:19081","dns":{"domains":["v.example.test"],"resolvers":["1.1.1.1:53"]}}`,
		`{"mode":"dns","listen":"127.0.0.1:65535","dns":{"domains":["v.example.test"],"resolvers":["1.1.1.1:53"],"key":"a-test-encryption-key-long-enough"}}`,
		`{"mode":"dns","listen":"127.0.0.1:19082","dns":{"domains":["v.example.test"],"resolvers":["1.1.1.1:53"],"key":"a-wrong-sized-key-for-aes-256-gcm"}}`,
	} {
		var c Config
		if err := json.Unmarshal([]byte(raw), &c); err == nil && c.Validate() == nil {
			t.Fatalf("accepted unsafe or incomplete config: %s", raw)
		}
	}
}

func TestVKForcesManualCaptchaAndDisablesSecondaryTunnel(t *testing.T) {
	c := Config{Mode: "vk", Listen: "127.0.0.1:19081", VK: json.RawMessage(`{"peer":"127.0.0.1:56000","clientId":"test-client","vk":{"manualCaptcha":false,"autoCaptcha":true,"advancedCaptcha":true},"tunnel":{"mode":"wg","config":"secret"},"routes":true}`)}
	data, err := c.VKJSON()
	if err != nil {
		t.Fatal(err)
	}
	var v map[string]any
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatal(err)
	}
	vk := v["vk"].(map[string]any)
	if vk["manualCaptcha"] != true || vk["autoCaptcha"] != false || vk["advancedCaptcha"] != false {
		t.Fatal("automated CAPTCHA was allowed")
	}
	if v["routes"] != false || v["tunnel"].(map[string]any)["mode"] != "none" {
		t.Fatal("secondary TUN/routes were allowed")
	}
	if v["proxy"].(map[string]any)["listen"] != c.Listen {
		t.Fatal("listener did not stay on the owned loopback port")
	}
}

func TestVKUsesBondForMultipleTCPSessionsAndPreservesLegacyOptOut(t *testing.T) {
	for _, test := range []struct {
		proxy string
		n     int
		want  bool
	}{
		{`{"mode":"tcp"}`, 6, true},
		{`{"mode":"tcp","bond":false}`, 6, false},
		{`{"mode":"tcp"}`, 1, false},
		{`{"mode":"udp"}`, 6, false},
	} {
		raw := fmt.Sprintf(`{"peer":"127.0.0.1:56000","clientId":"test-client","proxy":%s,"turn":{"n":%d}}`, test.proxy, test.n)
		c := Config{Mode: "vk", Listen: "127.0.0.1:19081", VK: json.RawMessage(raw)}
		data, err := c.VKJSON()
		if err != nil {
			t.Fatal(err)
		}
		var got map[string]any
		json.Unmarshal(data, &got)
		enabled, _ := got["proxy"].(map[string]any)["bond"].(bool)
		if enabled != test.want {
			t.Fatalf("proxy=%s streams=%d bond=%t want=%t", test.proxy, test.n, enabled, test.want)
		}
	}
}
