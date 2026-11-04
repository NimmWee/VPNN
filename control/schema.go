package control

import "encoding/json"

type Group struct {
	ID       string                     `json:"id"`
	Name     string                     `json:"name"`
	Calls    []string                   `json:"calls"`
	Profiles map[string]json.RawMessage `json:"profiles"`
}

type Device struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	Group      string `json:"group"`
	Enabled    bool   `json:"enabled"`
	TokenHash  string `json:"tokenHash"`
	UUID       string `json:"uuid"`
	WGPrivate  string `json:"wgPrivate"`
	WGPublic   string `json:"wgPublic"`
	WGIPv4     string `json:"wgIPv4"`
	DNSKey     string `json:"dnsKey"`
	DNSPort    int    `json:"dnsPort"`
	LastSeen   int64  `json:"lastSeen,omitempty"`
	AckVersion int64  `json:"ackVersion,omitempty"`
}

type Invite struct {
	DeviceID  string `json:"deviceId"`
	Token     string `json:"token"`
	PublicKey string `json:"publicKey"`
}

type Node struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	Group      string `json:"group"`
	Enabled    bool   `json:"enabled"`
	TokenHash  string `json:"tokenHash"`
	LastSeen   int64  `json:"lastSeen,omitempty"`
	AckVersion int64  `json:"ackVersion,omitempty"`
}

type NodeInvite struct {
	NodeID    string `json:"nodeId"`
	Token     string `json:"token"`
	PublicKey string `json:"publicKey"`
}

type NodeDevice struct {
	ID       string `json:"id"`
	UUID     string `json:"uuid"`
	DNSLabel string `json:"dnsLabel"`
	DNSKey   string `json:"dnsKey"`
	DNSPort  int    `json:"dnsPort"`
}

type NodePayload struct {
	Schema    int          `json:"schema"`
	NodeID    string       `json:"nodeId"`
	Group     string       `json:"group"`
	Version   int64        `json:"version"`
	IssuedAt  int64        `json:"issuedAt"`
	ExpiresAt int64        `json:"expiresAt"`
	Devices   []NodeDevice `json:"devices"`
}

type Profile struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Config string `json:"config"`
}

type Payload struct {
	Schema           int       `json:"schema"`
	DeviceID         string    `json:"deviceId"`
	Version          int64     `json:"version"`
	IssuedAt         int64     `json:"issuedAt"`
	ExpiresAt        int64     `json:"expiresAt"`
	Profiles         []Profile `json:"profiles"`
	RefreshAfter     int64     `json:"refreshAfter,omitempty"`
	ControlEndpoints []string  `json:"controlEndpoints,omitempty"`
}

type Envelope struct {
	Payload   string `json:"payload"`
	Signature string `json:"signature"`
}

type diskState struct {
	Version    int64              `json:"version"`
	NextDevice int                `json:"nextDevice"`
	Groups     []Group            `json:"groups"`
	Devices    map[string]*Device `json:"devices"`
	Nodes      map[string]*Node   `json:"nodes"`
}
