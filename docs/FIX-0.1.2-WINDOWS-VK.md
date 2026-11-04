# VPNN 0.1.2+3 — Windows routing and VK reconnect

User report: Windows/Chrome showed the home IP while VPNN reported transport ready; switching DNS/VK requested CAPTCHA again. Another VPN was off during the test. The old app was already disconnected during inspection; its empty current OS proxy state is not evidence of an active-session proxy failure.

## Confirmed code defects and changes

- Managed Windows start delegated to SetupAction without requesting TUN. The saved desktop setting had tun.enable=false. Proxy-only startup did not meet the product's system-VPN expectation.
- Managed Windows start now requests TUN through the existing owner, uses rule mode and enables IPv6 with the explicit general override so IPv6 is captured too. SAFE_MODE remains inert. Authorization failure stops the owner and reports a capture error; protocol fallback does not repeat permission requests.
- Native status now includes captureReady based on the running lifecycle and actual TUN listener configuration on Windows, and on the service/protect readiness on Android. A ready transport without capture is rejected, and loss of capture stops the managed run. The view excludes known failed capture from its connected status.
- FreeTurn recreated a fresh VK credential Store for each provider/session. A regression reproduced two VK authentication requests for two starts of the same identity.
- Successful, unexpired TURN credentials can now be reused across mode switches within the same Core process. The cache is bounded to 32 scopes and separated by device fingerprint, call link, platform, state directory, credentials and policy. No temporary TURN secrets are written to disk. Original expiration and rejection/deallocation invalidation remain enforced.

## Verification

- Both Windows regressions failed before the fix: no TUN requested; ready-without-capture accepted. The VK reconnect regression also failed with two fetches instead of one.
- 179 selected Flutter tests passed, including Windows owner/authorization/SAFE_MODE checks, capture-loss/no-fallback checks, SetupAction, system proxy queue, routed health and localization. flutter pub get completed; flutter analyze reported no issues.
- Core focused tests passed, including a non-omitted false captureReady field and existing Windows socket protection tests. Engine tests and vet passed.
- FreeTurn VK/provider/session/mobile tests passed, including cache reuse, expiry, invalidation, isolation, memory bounds and absence of credential files.
- Signed Android 0.1.2 release passed fresh offline-bootstrap + DNS HTTPS on the owned API35 emulator with direct VPS blocked; a second independent test rejected HTTPS outside tun0 and still reached the VPS. Temporary firewall rules were removed.
- Windows 0.1.2+3 built; its Core/helper manifest matches the packaged Core hash. The agent did not start a normal Windows VPN, change host routes/proxy or close the user's old VPNN process.

## User verification still required

Fully exit the old app through the tray, extract the complete new Windows ZIP into its own folder, run VPNN.exe, allow the administrator request, connect DNS, then make a fresh IP-check request. Expected IPv4 egress is 89.125.120.163. Report the capture error if one appears instead of a connection; do not treat readiness of the embedded transport as a routing test.

For VK, complete one successful authorization and connection before testing quick DNS/VK switches. A new challenge is still possible after credentials expire (about nine minutes with the safety margin), VK rejects them, release of an old allocation cannot be confirmed, or the Core/app restarts. An unfinished CAPTCHA produces no valid credentials to reuse. This change does not solve or bypass CAPTCHA.

Public server protocols and private device identities did not change. No server reinstall or new VPS is required.
