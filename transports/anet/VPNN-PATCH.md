# VPNN Android compatibility patch

Base: github.com/wlynxg/anet v0.0.5 (module checksum in the parent go.sum), MIT license retained.

Removed only the two `go:linkname` directives exposing private Go and x/net IPv6 zone-cache globals. Modern Go rejects these unsupported references when linking Android. Interface enumeration and ioctl/netlink fallbacks are retained; the caches are now local to anet. We do not disable Go's global linker checks.

Scope: VPNN unicast transport use. The upstream workaround for updating Go's private named IPv6 zone/multicast caches is intentionally unavailable. Do not claim scoped link-local IPv6 multicast support from this fork. Verify Android IPv4/IPv6 unicast separately on actual networks.

Upstream report: https://github.com/wlynxg/anet/issues/11
