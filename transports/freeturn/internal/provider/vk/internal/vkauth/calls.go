package vkauth

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"strconv"
	"strings"
	"time"

	fhttp "github.com/bogdanfinn/fhttp"
	tlsclient "github.com/bogdanfinn/tls-client"
	"github.com/google/uuid"
	"github.com/samosvalishe/free-turn-proxy/internal/provider/vk/internal/namegen"
	"github.com/samosvalishe/free-turn-proxy/internal/provider/vk/internal/personanet"
)

type callsHTTPClient interface {
	Do(*fhttp.Request) (*fhttp.Response, error)
}
type callsChainFn func(context.Context, string, tlsclient.CookieJar) (string, string, []string, error)

func (c *Client) getCallsTokenChain(parent context.Context, link string, jar tlsclient.CookieJar) (string, string, []string, error) {
	ctx, cancel := context.WithTimeout(parent, 35*time.Second)
	defer cancel()
	profile := c.currentPersona()
	client, err := personanet.NewClient(profile, c.dialer, jar, personanet.NoFollowRedirects())
	if err != nil {
		return "", "", nil, errors.New("VK Calls HTTP initialization failed")
	}
	defer client.CloseIdleConnections()
	return fetchVKCallsCredentials(ctx, client, link, profile.UserAgent)
}

func fetchVKCallsCredentials(ctx context.Context, client callsHTTPClient, link, ua string) (string, string, []string, error) {
	device := uuid.NewString()
	name := namegen.Generate()
	query := url.Values{"v": {"5.276"}, "client_id": {"8093730"}, "link": {"https://vk.ru/call/join/" + link}, "device_id": {device}, "anonymName": {name}, "lang": {"en"}}
	response, err := callsRequest(ctx, client, "https://api.vk.me/method/auth.getAnonymToken", query, ua)
	if err != nil {
		return "", "", nil, err
	}
	anon, err := callsString(response, "response", "token")
	if err != nil {
		return "", "", nil, err
	}
	query.Del("client_id")
	query.Del("anonymName")
	query.Set("anonymous_token", anon)
	query.Set("extended", "1")
	query.Set("fields", "first_name,last_name,photo_200")
	response, err = callsRequest(ctx, client, "https://api.vk.me/method/messages.getCallPreview", query, ua)
	if err != nil {
		return "", "", nil, err
	}
	secret, err := callsString(response, "response", "secret")
	if err != nil {
		return "", "", nil, err
	}
	preview, _ := response["response"].(map[string]any)
	id, ok := preview["user_id"].(float64)
	if !ok || id < -9007199254740991 || id > 9007199254740991 || id != float64(int64(id)) {
		return "", "", nil, errors.New("VK Calls invalid preview identity")
	}
	query.Del("extended")
	query.Del("fields")
	query.Set("name", name)
	query.Set("user_id", strconv.FormatInt(int64(id), 10))
	query.Set("secret", secret)
	response, err = callsRequest(ctx, client, "https://api.vk.me/method/messages.getAnonymCallToken", query, ua)
	if err != nil {
		return "", "", nil, err
	}
	token, err := callsString(response, "response", "token")
	if err != nil {
		return "", "", nil, err
	}
	sessionData, _ := json.Marshal(map[string]any{"version": 2, "device_id": uuid.NewString(), "client_version": "1.0.1"})
	query = url.Values{"session_data": {string(sessionData)}, "method": {"auth.anonymLogin"}, "format": {"JSON"}, "application_key": {"CGMMEJLGDIHBABABA"}}
	response, err = callsRequest(ctx, client, "https://calls.okcdn.ru/fb.do", query, ua)
	if err != nil {
		return "", "", nil, err
	}
	session, err := callsString(response, "session_key")
	if err != nil {
		return "", "", nil, err
	}
	query = url.Values{"joinLink": {link}, "isVideo": {"false"}, "protocolVersion": {"5"}, "anonymToken": {token}, "method": {"vchat.joinConversationByLink"}, "format": {"JSON"}, "application_key": {"CGMMEJLGDIHBABABA"}, "session_key": {session}}
	response, err = callsRequest(ctx, client, "https://calls.okcdn.ru/fb.do", query, ua)
	if err != nil {
		return "", "", nil, err
	}
	user, err := callsString(response, "turn_server", "username")
	if err != nil {
		return "", "", nil, err
	}
	password, err := callsString(response, "turn_server", "credential")
	if err != nil {
		return "", "", nil, err
	}
	turn, _ := response["turn_server"].(map[string]any)
	raw, _ := turn["urls"].([]any)
	addresses := make([]string, 0, len(raw))
	seen := map[string]bool{}
	for _, item := range raw {
		value, ok := item.(string)
		if !ok || (!strings.HasPrefix(value, "turn:") && !strings.HasPrefix(value, "turns:")) {
			continue
		}
		address := strings.TrimPrefix(strings.TrimPrefix(strings.SplitN(value, "?", 2)[0], "turn:"), "turns:")
		host, port, err := net.SplitHostPort(address)
		n, e := strconv.Atoi(port)
		if err != nil || host == "" || e != nil || n < 1 || n > 65535 || seen[address] {
			continue
		}
		seen[address] = true
		addresses = append(addresses, address)
	}
	if len(addresses) == 0 {
		return "", "", nil, errors.New("VK Calls returned no valid TURN addresses")
	}
	return user, password, addresses, nil
}

func callsRequest(ctx context.Context, client callsHTTPClient, endpoint string, params url.Values, ua string) (map[string]any, error) {
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	req, err := fhttp.NewRequestWithContext(ctx, "POST", endpoint+"?"+params.Encode(), nil)
	if err != nil {
		return nil, errors.New("VK Calls request initialization failed")
	}
	req.Header.Set("User-Agent", ua)
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Accept-Language", "en-GB,en;q=0.9")
	response, err := client.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, errors.New("VK Calls network request failed")
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("VK Calls HTTP status %d", response.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(response.Body, (1<<20)+1))
	if err != nil || len(data) > 1<<20 {
		return nil, errors.New("VK Calls invalid response body")
	}
	var result map[string]any
	if json.Unmarshal(data, &result) != nil {
		return nil, errors.New("VK Calls invalid JSON response")
	}
	if object, ok := result["error"].(map[string]any); ok {
		if terminal := classifyLinkError(object); terminal != nil {
			return nil, terminal
		}
		if apiErrCode(object) == 6 || apiErrCode(object) == 29 {
			return nil, ErrVKRateLimit
		}
		return nil, fmt.Errorf("VK Calls API rejected request (code %d)", apiErrCode(object))
	}
	return result, nil
}

func callsString(object map[string]any, path ...string) (string, error) {
	var value any = object
	for _, key := range path {
		m, ok := value.(map[string]any)
		if !ok {
			return "", fmt.Errorf("VK Calls missing response field: %s", strings.Join(path, "."))
		}
		value = m[key]
	}
	s, ok := value.(string)
	if !ok || s == "" {
		return "", fmt.Errorf("VK Calls missing response field: %s", strings.Join(path, "."))
	}
	return s, nil
}

func credentialExpiry(username string, now time.Time) time.Time {
	fallback := now.Add(CredentialLifetime - CacheSafetyMargin)
	prefix, _, found := strings.Cut(username, ":")
	if !found {
		return fallback
	}
	timestamp, err := strconv.ParseInt(prefix, 10, 64)
	if err != nil || timestamp <= 0 {
		return fallback
	}
	expiry := time.Unix(timestamp, 0).Add(-CacheSafetyMargin)
	if limit := now.Add(8 * time.Hour); expiry.After(limit) {
		return limit
	}
	return expiry
}
