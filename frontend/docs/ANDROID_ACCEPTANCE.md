# BetGuard: Android acceptance

Run mobile commands below from `frontend/`. See [mobile setup](../README.md).

Status: **USB/Metro startup confirmed by the user; manual enforcement checks remain pending**. The new manual-enforcement native build has not been tested on-device. Also check both themes, persistent appearance, launcher icons, large text, TalkBack, keyboard layout and reduced motion on the phone. Passing source checks does not demonstrate VPN routing.

Record the date, phone/emulator model, Android version, browser/version, Wi-Fi/mobile network, Private DNS setting, browser secure-DNS setting, IPv4/IPv6 behavior, and app commit/package version. Use a test phone/network you control. These tests change only that phone's routing after Android's VPN consent.

## Short manual block -> request -> unblock checklist

Install the updated development APK first; Metro alone cannot update Kotlin/bridge behavior. Use harmless `example.com` and a separately reachable control domain. A manual test block does **not** classify either site as gambling. Record actual observations beside each item; all enforcement items are currently pending.

1. With protection off, confirm the test hostname and control site load. Record exact hosts after redirects and any existing test rules so they can be restored.
2. Save a Block rule for the test hostname (choose exact or include-subdomains deliberately), then enable protection and grant Android VPN consent. Saving alone should create RULE SAVED/UPDATED, not BLOCKED BY RULE.
3. Trigger a fresh browser DNS lookup under the supported conditions below. Confirm the test request is blocked and the control is still reachable; a cached page or an open connection is inconclusive.
4. Confirm a corresponding BLOCKED BY RULE event with matching hostname/time. A resolver error is not a successful policy block. Capture browser and history evidence together.
5. Change the rule to Allow without restarting protection. Trigger a fresh lookup and confirm access returns when upstream DNS is available; inspect the upstream DNS response event.
6. Remove the override. Read the native effective-rule reason in feedback/Check: default Allow if no parent matches, otherwise the most-specific applicable parent rule. Test a parent block plus child allow, then remove the child and confirm the parent returns.
7. Save a test rule again, close/reopen and force-stop/reopen the app, and verify the saved rule and scope remain. After process termination protection requires explicitly enabling again.
8. Enable and then stop protection. Confirm Stopping resolves to Protection is off; also test the notification Stop action. Denied consent/revocation/start failure must never show a successful active state.
9. Switch Wi-Fi/mobile data while making fresh requests. Record recovery, errors and actual status. Restore original test rules and any DNS settings changed for this controlled run.

For the controlled ordinary-DNS test, first record Android Private DNS and the browser's Secure DNS settings. Temporarily turn them off if they bypass the virtual resolver, and restore their original values afterwards. Close existing browser connections and clear/restart browser DNS state as supported by that browser; app refresh alone does not flush all DNS/negative caches. Do not erase app storage or clear all personal browsing data just to force a lookup. If a fresh lookup cannot be demonstrated, mark the result inconclusive. Other apps and the network may also cache DNS.

## Supported feasibility path

The service routes IPv4 UDP packets addressed to its virtual resolver, `10.77.0.2:53`. It reads each question, evaluates the current manual rule, and writes an NXDOMAIN response for a blocked hostname. Other questions are forwarded to `1.1.1.1` over a protected UDP socket with a two-second timeout. Resolver failures produce SERVFAIL and a degraded status; they must not count as successful blocks or non-gambling predictions.

It does not intercept browser DNS-over-HTTPS, Android Private DNS, arbitrary external resolvers, DNS-over-TCP, raw IP destinations, or existing connections. IPv6 application traffic is allowed outside this narrow VPN route; an AAAA query sent to the IPv4 virtual DNS resolver can still be evaluated. Encrypted website paths are not inspected. Unsupported DNS packets may time out. IPv6-only/NAT64 networks, captive portals, and networks that disallow the selected resolver need further design and testing.

For the first controlled test, record and temporarily disable Private DNS/secure DNS on the test device/browser if needed to make ordinary DNS requests. Restore the original settings afterwards. This is a declared test condition, not evidence of bypass-proof protection. Do not enable Android's "block connections without VPN" option for this split-route feasibility filter.

## Build and launch gate

| Check | Expected result | Observed result |
| --- | --- | --- |
| `npm ci` | Dependencies match the committed lockfile | Pending |
| `npm run android` | Debug app builds, installs, and opens | Pending |
| First launch | No seeded rules/history; protection off | Pending |
| Deny VPN permission | Remains off; explains denial | Pending |
| Grant VPN permission | Foreground service starts; actual native status shown | Pending |
| Notifications denied | App remains usable; document how status/Stop is accessible | Pending |

## Enforcement and user-control gate

Use `example.com` as the harmless blocked test domain and another independently reachable domain as the allowed control. Establish reachability before enabling the VPN. Use a new DNS lookup after each rule change: an already open page, cached DNS answer, or reused connection is not a fresh enforcement test. Record exact hostnames after redirects.

| ID | Action | Expected result | Observed result |
| --- | --- | --- | --- |
| D01 | Save exact block for `example.com` with protection off | Rule saved; no DNS-block event fabricated | Pending |
| D02 | Enable protection and request `example.com` through the supported path | DNS-block event; matching fresh request fails resolution | Pending |
| D03 | Request the allowed control domain | Actual resolver response; site loads if network is healthy | Pending |
| D04 | Allow `example.com`, then make a fresh DNS request | Allow persists; a resolver response replaces policy blocking | Pending |
| D05 | Block parent with subdomains, allow a more specific child | Child's allow wins; sibling remains blocked | Pending |
| D06 | Remove child's override | Parent block applies again; not an unconditional unblock | Pending |
| D07 | Close and reopen the React UI | Native service and saved rules remain independent of the screen | Pending |
| D08 | Switch Wi-Fi/mobile data during requests | Rules persist; actual recovery and any request failures recorded | Pending |
| D09 | Disable network or make resolver unavailable | Degraded/error, not a successful block | Pending |
| D10 | Revoke VPN access or activate another VPN | Interrupted/off reported; no stale active claim | Pending |
| D11 | Stop from app and notification | Tunnel closes; saved rules remain | Pending |
| D12 | Terminate process/reboot, then reopen | Saved rules reload; protection stays off until enabled again | Pending |
| D13 | Clear history while off | History empty; rules preserved | Pending |
| D14 | Check valid and invalid links | Native normalization, truthful catalog/model/unknown source; unavailable is distinct from unknown and no rule changes silently | Pending |
| D15 | Change block/allow during an in-flight resolver request | Final response follows the latest matching manual rule | Pending |

Record bypass behavior separately: encrypted DNS, cached pages, established connections, direct-IP access, TCP DNS fallback, redirects to a different domain, and unsupported networks. A blocked DNS request is not a count of unique websites or proof of a blocked page visit. The app's displayed count covers only the retained last 200 history entries.

## Evidence required to close the milestone

- Successful debug build log and first-launch screenshot.
- External-browser blocked/control/unblocked evidence plus corresponding app history.
- Persistence, revocation, and network-transition observations.
- Supported configurations and unresolved issues explicitly listed.

M1 stays open until the device evidence exists. Do not begin reporting gambling-detection accuracy from these manual rules.

## Stable and development variants

Follow [the development workflow](DEVELOPMENT_WORKFLOW.md). Verify `com.betguard` (BetGuard) and `com.betguard.dev` (BetGuard Dev) are both installed, launch separately and retain separate Room/settings data. Reinstall Dev and confirm stable data is unchanged. Stop Metro and unplug USB; preview must still launch and manual protection must work with the backend unavailable. Test both identities' VPN consent and notification Stop action, one active VPN at a time. These new-variant device checks remain pending.
