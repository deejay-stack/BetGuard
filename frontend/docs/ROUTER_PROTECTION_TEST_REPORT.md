# Router Protection implementation and verification report

Date: 7 October 2026. This is an OpenWrt prototype extension of BetGuard.

**Software verification passed. Physical OpenWrt acceptance is pending: the available ISP/home router has not been confirmed compatible, and no router configuration was changed. Zero physical Router Protection clients were tested.** The administrator Android phone was used to verify navigation and existing Device/phone-proxy behavior; it was not a protected OpenWrt client.

## Architecture discovered

React Native provides four main tabs, hidden task screens, and the Kotlin bridge. Android Room owns saved Block/Allow rules and bounded Device/Hotspot activity. `BetGuardVpnService` handles the phone's supported DNS requests; `BetGuardNetworkService` is a separate HTTP/CONNECT proxy for explicitly configured clients. Both use local rules before the existing FastAPI domain endpoint in smart mode. FastAPI loads the shared `BetGuardRuntime` during lifespan startup; the verified blocklist, baseline model, cache and frozen decision engine determine ALLOW, ALLOW + WARN or BLOCK. Link checks and app-metadata review remain separate from enforcement.

## Architecture added

```text
Client joins authorized OpenWrt Wi-Fi normally
  → router DNS interception / dnsmasq
  → dedicated LAN BetGuard UDP/TCP DNS listener
  → synchronized replica of the phone's canonical Room rules
  → existing BetGuardRuntime for unmatched domains
  → NXDOMAIN for BLOCK; public resolution for ALLOW / ALLOW + WARN
  → Router activity and warning review on the administrator phone
```

The administrator app manages the service through authenticated existing FastAPI routes. The backend securely manages a supported router through HTTPS ubus, verifies its applied settings and observed DNS decisions, and stores a durable restoration journal. Client source attribution uses trusted router EDNS subnet options; those private options are removed before upstream resolution. There is no second ML model or separately editable router blocklist. Runtime artifacts and ML source were not modified.

## Files created

| Path from project root | Purpose |
| --- | --- |
| `backend/app/router/__init__.py` | Router module boundary. |
| `backend/app/router/base.py` | Adapter protocol and safe errors. |
| `backend/app/router/config.py` | Optional explicit listener, approved peers, token and CA settings. |
| `backend/app/router/openwrt.py` | Verified HTTPS ubus authentication, inspection, preview, apply, live verification and exact restoration. |
| `backend/app/router/dns.py` | Bounded UDP/TCP DNS filtering using the shared policy, upstream resolution and private client attribution. |
| `backend/app/router/policy.py` | Most-specific canonical rule replica, followed by the existing runtime. |
| `backend/app/router/store.py` | Private SQLite restoration journal, rule replica, bounded history and requesting clients. |
| `backend/app/router/service.py` | Setup state machine, health monitoring, apply/restore gating and recovery. |
| `backend/app/api/router_protection.py` | Bearer-authenticated status, connect, apply, verify, stop and policy routes; credential-safe validation errors. |
| `backend/tests/test_router_protection.py` | Adapter, real DNS socket, runtime, policy, recovery, concurrency and API verification. |
| `frontend/src/api/router.ts` | Validated snapshots and bounded authenticated service calls. |
| `frontend/src/state/RouterProtectionContext.tsx` | Session-only service token, Room snapshot synchronization, serialized actions and status refresh. |
| `frontend/src/screens/RouterProtectionScreen.tsx` | Guided authorization, secure connect, separate preview approval, health, clients, warning review and hold-to-restore. |
| `frontend/__tests__/RouterProtection.test.tsx` | UI, preview approval, warning rule edits and API/snapshot contracts. |
| `frontend/docs/ROUTER_PROTECTION.md` | Setup prerequisites, exact terminals, architecture, settings, restoration, limitations and defense demonstration. |
| `frontend/docs/ROUTER_PROTECTION_TEST_REPORT.md` | This evidence and acceptance report. |

## Files changed

| Path from project root | Reason |
| --- | --- |
| `.gitignore` | Exclude the private router journal directory. |
| `backend/.env.example` | Document optional router settings using public placeholders; no passwords. |
| `backend/app/main.py` | Add optional lifecycle integration and routes, preserving existing API startup when the router module is unavailable. |
| `backend/pyproject.toml`, `backend/requirements.lock.txt` | Pin the DNS parser `dnslib==0.9.26`. |
| `frontend/App.tsx` | Add the Router provider and hidden screen while preserving four main destinations. |
| `frontend/app.version.json` | Version the saved APK as 1.5.0. |
| `frontend/src/screens/HomeScreen.tsx` | Explain and expose the Router/Hotspot choices through the existing Network Protection entry. |
| `frontend/src/screens/NetworkProtectionScreen.tsx` | Add the method selector above existing proxy setup and controls. |
| `frontend/src/screens/HistoryScreen.tsx` | Merge source-tagged router history and add Device/Hotspot/Router filters. |
| `frontend/src/components/ActivityRow.tsx` | Render router outcomes and source labels. |
| `frontend/src/components/HowItWorks.tsx` | Explain the three modes and router setup. |
| `frontend/src/state/types.ts` | Add the router activity source type. |
| `frontend/docs/APP_GUIDE.md` | Link the router guide and explain compatibility. |
| `frontend/docs/NETWORK_PROTECTION.md` | Preserve the phone proxy guide and link the separate router workflow. |
| `frontend/docs/NETWORK_PROTECTION_TEST_REPORT.md` | Retain the earlier proxy evidence and recent troubleshooting results. |

The real backend `.env`, native services, existing database schema, training scripts, datasets, models and decision thresholds were preserved. Changes present before this task in Home, Network Protection, their documents and versioning were retained.

## Exact router changes and restoration

No changes were applied to the available ISP router. The implemented adapter previews these changes on an explicitly authorized compatible OpenWrt router:

1. Selected dnsmasq `server` becomes the dedicated LAN filter address and port; `noresolv=1`, `cachesize=0`, `addsubnet=32,128`, `stripsubnet=1`.
2. LAN DHCP option 6 advertises the router's actual DNS address while retaining other DHCP options.
3. One uniquely named `bg_dns_<random>` LAN firewall redirect sends conventional TCP/UDP destination port 53 to local dnsmasq port 53, family `any`.

The journal records original option presence, scalar/list values, router HTTPS address and LAN MAC identity before mutation. Apply requires a current preview, explicit approval, ready runtime/listener and acknowledged phone rules. ACTIVE requires verified UCI values, the live nftables rule and fresh router-origin Wikipedia ALLOW and Stake BLOCK DNS observations. An unconfirmed initial UCI apply has a 60-second rollback window.

Stop restores the saved presence/values/lists, removes only BetGuard's unchanged redirect, reloads dnsmasq/firewall, verifies original values and the disappearance of its live rule, then reports OFF. Unrelated settings remain untouched; concurrent edits to touched settings are refused. Recovery on a different router at the same IP is refused. Failed/offline restoration keeps the journal and recovery-required status. A backend restart requires secure reauthentication; passwords and RPC session tokens are never saved in the journal. Closing the phone app does not silently restore a router.

## Automated verification

Commands run from the indicated directories:

```powershell
# backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe ..\ml\src\test_runtime_service.py

# frontend
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test -- --runInBand

# frontend/android, with JAVA_HOME pointing at JDK 21
.\gradlew.bat :app:testDevelopmentDebugUnitTest -PreactNativeArchitectures=arm64-v8a --max-workers=2 --console=plain
```

| Check | Actual result |
| --- | --- |
| Complete backend suite | **144 passed, 1 skipped**; the original suite was 124 passed, 1 skipped. |
| Router backend cases | **20 passed**, including parametrized cases. |
| Complete frontend suite after final UI edits | **149 passed**, 14 suites. |
| TypeScript / ESLint | Passed. |
| Native Android suite | **7 passed**; final Gradle run successful. |
| Existing ML runtime smoke | Passed; baseline, 359,736 verified gambling domains, 15 requests / 10 cache hits. |
| Existing model/data integrity | All **19** captured artifact/dataset/threshold SHA-256 comparisons unchanged. |

Router tests use the adapter's real inspection/apply/restore logic with simulated ubus responses, real local UDP/TCP sockets, and the existing frozen runtime. They cover two **simulated** client IPs, 20 concurrent DNS requests, ALLOW/WARN/BLOCK, canonical rule propagation, source ACL, private EDNS removal, upstream failure/SERVFAIL, alias blocking, exact and idempotent restore, restoration conflicts, router identity, HTTPS-only transport, untrusted TLS, live-rule checks, stale preview, false ACTIVE prevention, offline health, interrupted work, journal recovery and credential redaction. These are not physical OpenWrt tests.

Evidence is retained in the ignored project `verification/` directory: `router-final-backend-complete.log`, `router-final-router-tests.log`, `router-final-frontend-recheck.log`, `router-final-native.log`, `router-ml-runtime-smoke.log` and `router-ml-integrity.json`.

## Real-device evidence and pending acceptance

The connected realme C55 administrator phone opened **Home → Open Network Protection → Router Protection** and displayed the truthful not-configured state, guided service connection and separate Hotspot return control. No fake active router, clients or enforcement metrics were displayed. Existing four saved rules were retained.

| Physical Router Protection acceptance | Result |
| --- | --- |
| Compatible authorized router | Unavailable / OpenWrt unconfirmed. |
| Physical protected clients | **0**. |
| Allowed / blocked / warning website tests | Pending on real OpenWrt clients. |
| Rule propagation to two physical clients | Pending. |
| Actual client list / IPv6 / TCP interception | Pending. |
| Physical apply / restore | Pending; adapter and recovery are verified in software tests. |

Device regression on the phone enabled Smart protection through the existing VPN flow. DNS replies were Wikipedia `rcode=0`, Microsoft `rcode=0`, and Stake, wheeloffortunecasino.com and the existing example.com rule `rcode=3`. The external probe processes for Wikipedia and Microsoft were killed by Android after printing their successful reply; the reply observations are retained without claiming clean process exits. Protection was paused through its existing hold control afterward. These tests verify supported DNS outcomes, not full browser page loads or encrypted-DNS interception.

Hotspot/proxy regression started the existing phone gateway at its actual Wi-Fi address `192.168.1.4:8080`. Phone-origin CONNECT probes received `200 Connection Established` for Wikipedia and Microsoft, and `403 Request refused by BetGuard` for Stake, wheeloffortunecasino.com and the existing example.com rule. All five probe processes exited successfully. These were **self-probes with zero external client devices**; they confirm the listener and decision path but do not resolve the previous home-network peer-reachability or iPhone hotspot-internet issue. The existing hold-to-stop control stopped the gateway; Android's service listing then contained neither BetGuard protection service. Device/Hotspot were both off at the end, matching the starting state, and the original on-device selection and four rules were retained. Evidence: `verification/router-device-regression.json`, `router-hotspot-regression.json`, `router-proxy-stop.json` and local UI captures.

## Saved APK

The final build command was run from `frontend` after typecheck, lint and the complete frontend suite passed:

```powershell
$env:JAVA_HOME='C:\Program Files\Java\jdk-21'
$env:ANDROID_HOME="$env:LOCALAPPDATA\Android\Sdk"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-apk.ps1 -VersionName 1.5.0 -SkipChecks
```

Gradle reported **BUILD SUCCESSFUL**. Final artifact: `frontend/build/apk/BetGuard-v1.5.0-b14.apk`, arm64, 27,117,422 bytes. `BetGuard-latest.apk` points to a copy of this build, with a companion SHA-256 file. SHA-256:

```text
f78284659592b9c7ab880f350ea87b8a857e5bcaea41022ec93d1a40dff1f0a6
```

The APK was copied to the administrator phone's **Download/BetGuard-v1.5.0-b14.apk**. The intermediate build 13 is superseded by build 14, which includes the final Home wording, status refresh ordering and standalone API notice. No app was uninstalled or replaced. The existing installed USB debug app displayed the updated interface through Metro during phone checks. Installing the saved standalone APK replaces that app's code and uses its release API configuration; the current project has **no deployed HTTPS API address configured**, so online Smart/Router features require that deployment setting and a new build. On-device saved rules remain available. Saving an APK does not itself enable a router or provide internet.

For future changes, run `npm.cmd run apk:save` from `frontend`; its default workflow runs frontend checks and increments the build number. Use the USB debug workflow in the router guide for local-server testing. Build log: `verification/router-apk-final-build.log`.

## Limitations and demonstration

Use the [step-by-step defense checklist and exact terminal commands](ROUTER_PROTECTION.md#capstone-demonstration-and-acceptance-checklist). It explicitly requires an authorized compatible router, stable LAN server, HTTPS ubus with trusted certificate, actual before/after approval, two normally connected clients, warning review and verified restoration.

Conventional DNS TCP/UDP 53 is the supported path. DoH, DoT, DoQ, VPNs, alternative networks, cached answers and existing connections can bypass filtering. DNSSEC validation is not claimed. Locked ISP routers and complex multi-dnsmasq/zone configurations are unsupported. Availability depends on the dedicated LAN server, router and upstream DNS; server errors return SERVFAIL rather than a fabricated AI block. This bounded prototype is not a redundant production gateway. Device and manually configured Hotspot Protection remain separate fallback modes.
