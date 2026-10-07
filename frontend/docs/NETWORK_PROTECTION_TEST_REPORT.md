# Network Protection verification — October 7, 2026

This addition uses a separate Android foreground proxy service. The existing DNS VpnService, Room rules and FastAPI domain endpoint remain the decision paths. The React Native UI has a hidden Network route reached from Protection, retaining the four main tabs. No backend changes were needed for Network Protection, and the seven recorded model/threshold/list artifact hashes are unchanged.

Architecture and exact commands: [Network Protection guide](NETWORK_PROTECTION.md).

## Phone hotspot: passed on two physical clients

Host: Realme C55 / RMX3710, Android 13. Actual hotspot interface `ap0`, gateway `10.92.90.2:8080`. Laptop source `10.92.90.126`; additional client `10.92.90.55`, identified as an iPhone by the user. The user used Chrome on iOS. The phone shared its existing Wi-Fi internet during this test; a mobile-data-only uplink was not verified.

1. Enabled the phone hotspot, discovered its real interface/address, started the gateway from BetGuard, and confirmed foreground service ID 773.
2. User connected the laptop and iPhone. Laptop used explicit per-request proxy tests; no global Windows proxy configuration was changed. User configured the iPhone's Wi-Fi manual proxy.
3. Laptop Wikipedia HTTPS CONNECT succeeded; following its redirect returned HTTP 200. HTTP Wikipedia also forwarded and returned a normal HTTPS redirect.
4. Stake HTTPS CONNECT received BetGuard 403, with `verified_gambling_blocklist` source and laptop IP in history. The iPhone also recorded Stake blocks, and the user confirmed it did not open.
5. Microsoft CONNECT succeeded with `ml_warning`; the user confirmed it opened on the iPhone. This demonstrates the warning path, not a claim that Microsoft is gambling.
6. Selected Block Site for `microsoft.com` in Network Review. A persistent exact-hostname Room block was saved. The next laptop request received 403; the user confirmed a fresh iPhone request also failed. Existing tunnels are closed when a matching Block rule is saved.
7. Removed that temporary rule, requested the hostname again to exercise WARN, selected Always Allow, and verified the next request succeeded with `user_allowlist` in history. Removed the temporary allow rule afterward. The original four rules and their timestamps remained unchanged.
8. Temporarily removed USB backend forwarding. An unmatched Wikipedia request received 503, while the saved Microsoft test block still received 403. Restoring forwarding recovered allowed browsing. Errors were recorded as service failures, not AI blocks.
9. Navigated between Network Protection and Protection while the service remained active. Held Stop for 2.8 seconds through the 2.5-second control: UI returned Off and Android reported no active BetGuard services. Subsequent native update preserved rules/history.

Observed live diagnostics snapshot during the two-client session: **226 requests, 182 allowed, 43 blocked, 16 warnings, 1 request error, 0 rejected**. Warnings are included in Allowed. These are an observed session snapshot, not a total for the whole demonstration. The request error was an upstream connection failure to a Microsoft telemetry hostname. Background client requests are included; blocks are not unique visits.

## Actual model/API results

| Hostname | Enforcement | Intervention | Source | ML score |
| --- | --- | --- | --- | --- |
| stake.com | BLOCK | BLOCK | verified_gambling_blocklist | Not evaluated |
| wikipedia.org | ALLOW | NONE | ml_low_risk | 0.203321 |
| microsoft.com | ALLOW | WARN | ml_warning | 0.583148 |
| wheeloffortunecasino.com | BLOCK | BLOCK | ml_high_risk | 0.8425 |

The last hostname additionally verified a genuine model-based refusal with no manual rule. Cached API responses retained the same decisions. Server health showed cache hits increasing, using the existing runtime loaded once per server process. The model and gambling list were not loaded inside the Android service or for each request.

## Concurrency

Twenty simultaneous workers on the laptop sent 20 CONNECT requests: five each for the four hostnames above. All returned the expected result, with **10 established tunnels, 10 policy refusals, 5 allowed warnings, 0 request failures**; response times were approximately 0.185–0.473 seconds. This is one physical client with multiple connections, not twenty physical devices.

A native thread-safety test separately simulated twenty distinct client IPs with 400 requests: 200 blocks and 200 warnings, correct aggregate counts, expiry and open-connection retention. Two physical requesting devices were observed during the actual hotspot demonstration. Performance with 5–20 physical devices remains unverified.

## Home Wi-Fi: reachability investigation

After the hotspot test, the user connected the laptop and iPhone to ALIMA. Phone Wi-Fi `192.168.1.4/24`, laptop `192.168.1.11/24`. Started the same gateway on `wlan0`, `192.168.1.4:8080`, with the updated debug APK. Turned the hotspot off and confirmed the phone remained connected to ALIMA.

The laptop's three required proxy requests timed out before reaching BetGuard. Windows TCP test failed, ping reported DestinationHostUnreachable, and there was no ARP entry for the phone. Phone-to-laptop ping also failed. A raw request made on the phone to its own wlan0 listener received the correct Stake 403 with verified-list source; this self-check is not an additional physical client or evidence of external home-network access. This indicates a LAN reachability problem; client isolation is a possible explanation, not a confirmed router setting. Router credentials, DHCP/DNS and other router configuration were not changed.

The user confirmed that the iPhone could not open any of the three test sites with the home manual proxy and described the connection as very slow. No external home-client requests reached BetGuard. Therefore the home Wi-Fi demonstration **did not pass**; the Stake timeout here is not evidence of policy blocking. The phone listener works locally, but this ALIMA network did not provide demonstrated peer reachability. The user was instructed to turn the iPhone's ALIMA proxy Off to restore direct browsing. Repeat this phase on a LAN permitting direct device-to-device TCP connections before claiming home-network support is verified.

## Automated checks and APK

- Frontend typecheck and lint passed; all **144 tests across 13 suites passed**.
- Native tests: **7 tests, 0 failures/errors**, including six new proxy/tracker tests and the existing core test.
- Native parser tests cover opaque CONNECT payload preservation, HTTP origin-form forwarding, hop-header stripping, malformed/smuggled requests, unsupported destinations/ports, body/header limits and subnet checks.
- Room migration retained existing rule data and history; on-device database is schema version 2.
- Saved release APK: `frontend/build/apk/BetGuard-v1.4.0-b11.apk`, 27,087,454 bytes. SHA-256: `783f094c86f2e477c2dc84d5e3d214c008b782ec355c7b722c13a55659e5292a`.
- Matching developmentDebug build installed over BetGuard Dev without uninstalling. Standalone APK copied to the phone's Download folder.
- No public HTTPS backend URL is configured. The saved release requires that deployment to enable online Network/Smart Protection; the debug app uses existing USB localhost forwarding. The saved APK does not include the Python model/server.

## Files created

| Path (relative to frontend) | Purpose |
| --- | --- |
| android/app/src/main/java/com/betguard/filter/network/BetGuardNetworkService.kt | Bounded concurrent foreground HTTP/CONNECT service, reused detector/rules, teardown and rule-change enforcement |
| android/app/src/main/java/com/betguard/filter/network/ProxyProtocol.kt | Bounded strict HTTP parser, destination and subnet checks |
| android/app/src/main/java/com/betguard/filter/network/ClientTracker.kt | Thread-safe actual client activity/counts |
| android/app/src/main/java/com/betguard/filter/network/GatewayState.kt | Independent native gateway lifecycle, counters and snapshots |
| android/app/src/main/java/com/betguard/filter/network/LanInterfaces.kt | Dynamic hotspot/LAN address discovery |
| android/app/src/test/java/com/betguard/filter/NetworkProxyTest.kt | Parser, network-boundary and concurrency tests |
| android/app/schemas/com.betguard.filter.BetGuardDatabase/2.json | Room's generated migration schema |
| src/state/NetworkProtectionContext.tsx | Separate gateway native bridge state/events and notification permission |
| src/screens/NetworkProtectionScreen.tsx | Start/hold-stop, real endpoint, client list, review and diagnostics UI |
| __tests__/NetworkProtection.test.tsx | Gateway contract, warning rule reuse, stop/state and network history checks |
| docs/NETWORK_PROTECTION.md | Setup, architecture, commands, APK and limitations guide |
| docs/NETWORK_PROTECTION_TEST_REPORT.md | This evidence and change inventory |

Local verification helpers/evidence under the ignored `verification/` folder include `probe-network.py` for per-request concurrent TCP probes and `network-ui.py` for BetGuard UI checks. These are not shipped in the app.

## Files changed for this addition

| Path (relative to frontend) | Reason |
| --- | --- |
| App.tsx | Add hidden Network route/provider, retain main tabs |
| android/app/src/main/AndroidManifest.xml | Register separate connectedDevice foreground service and its permissions |
| android/app/src/main/java/com/betguard/filter/BetGuardDatabase.kt | Non-destructive migration adding nullable network history metadata |
| android/app/src/main/java/com/betguard/filter/RuleRepository.kt | Record network history using existing Room history/rule storage |
| android/app/src/main/java/com/betguard/filter/BetGuardModule.kt | Add separate gateway methods/events and initialize address discovery |
| specs/NativeBetGuard.ts | Add gateway bridge methods and event specification |
| src/state/types.ts | Optional client/protection/source metadata for shared history |
| src/state/nativeContract.ts | Validate additive network history metadata |
| src/screens/SitesScreen.tsx | Gateway entry point beside existing protection tools |
| src/screens/HistoryScreen.tsx | Device/Network source filters with existing outcome filters |
| src/components/ActivityRow.tsx | Network/Device badges, client IP and source/error copy |
| src/screens/HomeScreen.tsx | Keep Device counters based on DNS events, excluding network history |
| src/components/HoldButton.tsx | Optional gateway stop wording, retain existing hold defaults |
| src/components/HowItWorks.tsx | Add Device vs Network architecture and manual client setup instructions |
| docs/APP_GUIDE.md | Link the network guide |
| app.version.json | Shared version 1.4.0, build 11 |

Other uncommitted project changes predate this addition and were preserved. The FastAPI detector, runtime, backend authentication, classifier policy and Android Device VpnService were not rewritten for Network Protection.

## Remaining verification and limits

See the guide for explicit-proxy bypasses, no TLS interception, supported HTTP/HTTPS ports, bounded worker/idle limits, local-subnet access, no proxy authentication, background service restrictions and offline behavior. Invalid parser inputs are unit-tested; physical port-conflict, process-crash and mobile-data-only demonstrations were not all exercised. The remaining home-network demonstration requires a LAN that allows peer connections. No 5–20-physical-device or campus-wide enforcement claim is made.

## Device Protection regression: passed

With the updated debug APK installed and the separate Network foreground service still running on wlan0, enabled existing Smart Device Protection from Home through the existing permission explanation. Android reported both service records: Network foreground ID 773 and DNS/VPN foreground ID 771. Direct on-device DNS probes returned:

- `stake.com`: RCODE 3 / NXDOMAIN, verified-list block.
- `wikipedia.org`: RCODE 0, normal answer.
- `microsoft.com`: RCODE 0, warning allowed, with `dns_warning` in history.
- `wheeloffortunecasino.com`: RCODE 3, model-based block, with `ml_high_risk` in history.

The Home screen displayed DNS FILTER ACTIVE and the original four rules remained unchanged. This verifies that adding the gateway did not replace the Device service or alter its model enforcement policy.

## End-of-test state

Stopped Network Protection through the hold control while Device Protection remained active; Android then showed only the VPN service. Paused Device Protection separately; Android reported no remaining BetGuard service records and Home showed Protection Off. The hotspot is off and the laptop is back on ALIMA. FastAPI, Metro and USB forwarding remain available for development. The iPhone's proxy must be set Off by the user; its settings cannot be controlled through this Android USB connection.

Compared the final Room rule rows to the pre-feature phone database backup: **four before, four after, identical domains/actions/subdomain flags/timestamps**, schema version 2. Temporary Microsoft test overrides were removed. No app uninstall, destructive database migration or signing-key replacement was performed.
