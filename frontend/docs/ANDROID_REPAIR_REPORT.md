# BetGuard Android repair report

The October 6 guided interface and new versioned APK commands are documented in [APP_GUIDE.md](APP_GUIDE.md). This report remains the historical record of the October 5 repair and device tests.

Verified October 5, 2026 against a connected RMX3710, Android 13/API 33, arm64. This report covers the repair of the existing project, including the earlier integrated detector. No model training, dataset replacement, authentication change, dependency upgrade, database migration or cloud deployment was performed.

## Architecture inspected

| Area | Existing structure and ownership |
| --- | --- |
| Frontend | Bare React Native/TypeScript. App.tsx owns five bottom tabs; src/screens owns screens; src/components and src/theme.ts share UI; state providers consume the Android bridge. src/api/client.ts/config.ts, catalog.ts and domain.ts call the established backend. |
| Native Android | specs/NativeBetGuard.ts declares the TurboModule contract. BetGuardModule.kt implements it. BetGuardVpnService.kt creates the virtual IPv4 UDP DNS interface. DetectionClient.kt binds HTTP to an underlying non-VPN network. filter/core owns hostname normalization, rule matching, packet parsing and service state guards. |
| Phone storage | Room schema version 1 stores local allow/block rules, exact/subdomain scope and the latest 200 activity events. RuleRepository.kt owns access and emits snapshots. AppearancePreferences.kt uses native preferences. No user account is required by the existing app. |
| Backend | backend/app/main.py owns the single FastAPI app and lifespan. app/api/domain.py and app/services/domain_service.py adapt detection; schemas validate responses. Existing catalog routes, SQLAlchemy/psycopg, Alembic and private Supabase configuration remain separate. |
| ML | ml/src/runtime_service.py loads BetGuardRuntime once through FastAPI lifespan; decision_engine.py applies verified lists/model policy. Baseline char TF-IDF/logistic regression comes from models/baseline_domain_classifier.joblib, with the existing deployment metadata and runtime list. No Flask/second server is introduced. |

Inspection included native registration/codegen, installed APK methods, all screens and state providers, API clients, existing backend lifecycle/routes, ML paths and artifacts, Room schema, build profiles, signing configuration and existing tests before editing.

## Root causes and fixes

**DNS: undefined is not a function.** The installed older com.betguard APK contained checkLink but lacked configureDetection and resolveLink. JavaScript expected the newer contract. Metro reload cannot add Kotlin methods to an installed APK. A native v2 handshake now checks every required method before actions become available; incompatible builds show a clear rebuild/update message. A matching native APK was rebuilt and installed as BetGuard Dev.

**Check Link: could not read the current rule.** The same old APK lacked resolveLink, which the screen uses to refresh effective rules without recording duplicate checks. The previous catch message suggested a build problem for every exception. Calls now validate the bridge and returned data, keep current-rule synchronization, and translate/log actual action errors without exposing arbitrary input or private paths.

**VPN stuck on Stopping.** Physical testing found an additional lifecycle defect: stopService removed the started flag, but Android's VPN binding kept the service and tunnel alive. Stop now sends ACTION_STOP to the service, closes the TUN explicitly, shuts down sockets/workers/reader and removes the foreground notification before stopSelf. Cleanup is idempotent and also handles start failure, reader failure and revocation. OFF is published after interface closure. Two offline start/stop cycles and an online stop passed; dumpsys confirmed the VPN service was removed.

**Windows builds.** The previously selected SDK/build tools were unavailable locally. The configured toolchain is now API 36, Build-Tools 36.1.0 and NDK 27.3.13750724. Windows short paths can rename clang++ so its driver chooses C linking; an explicit C++ driver flag resolves the observed linker failure. Short native staging paths and CMAKE_OBJECT_PATH_MAX=250 resolve the observed release Ninja path-length failure. No React Native dependency was changed for the nonfatal FeatureFlags warning.

**Signing.** Android rejected an update to older com.betguard with INSTALL_FAILED_UPDATE_INCOMPATIBLE. Both the supplied frontend/android/app/debug.keystore and the user's global Android debug certificate differ from the old APK. The old installation and its data were retained; no uninstall or data clear was used. Matching Dev updates preserve Dev data. Its one original exact www.facebook.com block rule was separately recreated through the Dev UI for offline testing. Other old history remains in the old installation.

## Detection and enforcement

```text
Explicit URL/hostname -> native normalization and local rule read
                     -> existing HTTP clients
                     -> FastAPI /v1/check (catalog, independent)
                     -> FastAPI /v1/domain/check (finalized detector)
                     -> singleton runtime -> verified list -> unchanged ML
                     -> local rule has final UI/device priority

DNS packet -> most specific Room allow/block override
           -> if unmatched and online enabled: same FastAPI runtime
           -> BLOCK: NXDOMAIN, zero answers, blocked Activity event
           -> WARN: normal DNS forwarding, warning Activity event
           -> ALLOW: normal DNS forwarding
           -> detection unavailable: SERVFAIL + degraded/ERROR status

Manual mode -> Room rules -> unmatched DNS forwarded; backend not required
```

The server intentionally does not read device user-rule files; Room is the authority for those overrides. Runtime paths are anchored to the ML package/ML_ROOT, and FastAPI lifespan loads the model/list once. Model scores at or above 0.512117 trigger review; scores at or above 0.70 trigger blocking. Verified gambling entries block before ML. These existing thresholds and policy were preserved. All 19 baseline hashes covering checked models, metadata, runtime lists, processed data and external holdout files matched after this work.

| Input | Live detector | Real online phone DNS |
| --- | --- | --- |
| stake.com | BLOCK, verified gambling list | NXDOMAIN (rcode 3), 0 answers |
| www.stake.com | BLOCK, canonical stake.com | NXDOMAIN, 0 answers |
| https://stake.com | BLOCK, normalized stake.com | URL is checked as a hostname; stake DNS test above |
| https://www.stake.com/casino | BLOCK, normalized/canonical stake.com | Exact www.stake.com allow override returned answers; removing it restored NXDOMAIN |
| wikipedia.org | ALLOW/NONE, score 0.203321 | rcode 0, 1 answer |
| microsoft.com | ALLOW/WARN, score 0.583148 | rcode 0, 1 answer; warning recorded |

The Microsoft result says uncertainty and does not identify it as gambling. Always allow saved an allow override; Block site produced NXDOMAIN; removing the override restored allowed warning behavior. Local allow also overrode the verified Stake blocklist on the exact www hostname. These are observed network tests, not API-only claims. Fresh standalone UDP A queries were sent to 10.77.0.2:53; a separate Android system-resolver probe also failed to resolve Stake and resolved Wikipedia.

## UI and control behavior

- Five tabs: Home, Check link, Rules, Activity, Settings. Existing route identities and manual rule logic are retained.
- Home shows native OFF/STARTING/ON/STOPPING/ERROR, actual online/manual mode, rule count, recent DNS activity and retained-event blocked/warning counts. It labels counters as incomplete when history is pruned. Enabling offers manual rules or online detection when configured; Android owns VPN consent.
- Check link separates normalized domain, effective local rule and detector decision. Blocking recommendations and saved rules are distinguished from actual blocked traffic. Catalog availability is independent from detection. Scores/catalog internals are collapsed under technical details.
- WARN actions: Go back resets the check and returns Home; Continue once opens only the normalized HTTPS hostname and persists no rule; Always allow/Block site save existing Room rules with existing subdomain scope preserved. It does not create a temporary bypass for an already blocked site.
- Rules retains add/edit/remove and exact/subdomain controls. Removing an override explains the online/manual fallback.
- Activity provides All/Blocked/Warnings/Allowed/Other filters, compact reasons, relative time and expandable details. Warning rows explicitly say access was allowed.
- Settings groups protection, website rules, appearance, notifications, privacy and about. Navigation buttons open their actual tabs; Android settings uses the system app settings page; clear history keeps the existing confirmation and rules.
- System/Light/Dark share central semantic colors for text, surfaces, allowed/review/blocked states. Native persistence supports all three choices. Light and dark layouts were inspected on the device; dark was retained after cold launch; System is the final preference.
- Loading/cancel/retry/empty/error states remain actionable. Required native functions and snapshot/link data are validated. Friendly errors accompany sanitized error-type logs; a render boundary offers Try again.

## Every changed or added file

Paths below are relative to betguard/. Generated APKs, screenshots, logs, APK backups and temporary automation are in ignored build/verification directories and are not source changes.

| File | Reason |
| --- | --- |
| .gitignore | Ignore local verification artifacts, including backups and screenshots. |
| frontend/.eslintrc.js | Exclude generated build directories at all nesting levels from source lint. |
| frontend/App.tsx | Apply the render boundary and clear five-tab labels. |
| frontend/specs/NativeBetGuard.ts | Declare synchronous native bridge version handshake. |
| frontend/android/build.gradle | Compatible installed SDK/toolchain; Windows C++ driver and shortened native build paths. |
| frontend/android/app/src/main/java/com/betguard/filter/BetGuardModule.kt | Expose bridge v2; send explicit service Stop intent and report stop failures. |
| frontend/android/app/src/main/java/com/betguard/filter/BetGuardVpnService.kt | Explicit, idempotent tunnel shutdown; truthful OFF/error lifecycle and sanitized failure logs. |
| frontend/android/app/src/main/java/com/betguard/filter/AppearancePreferences.kt | Persist System along with Light/Dark. |
| frontend/android/app/src/main/java/com/betguard/filter/RuleRepository.kt | Include actual configured detection mode in snapshots; no schema change. |
| frontend/src/state/nativeContract.ts (new) | Validate version, native methods, snapshots and link results; translate/log errors safely. |
| frontend/src/state/BetGuardContext.tsx | Guard native actions/subscriptions, validate returned state, friendly failures and accurate rule feedback. |
| frontend/src/state/ThemeContext.tsx | Persisted three-way preference; resolved theme follows device in System mode; guarded native errors. |
| frontend/src/state/types.ts | Detection mode field and readable native state labels. |
| frontend/src/theme.ts | Central semantic colors and cleaner shared typography/surfaces/spacing. |
| frontend/src/components/ui.tsx | Accessible selected buttons, retry status action and simpler header/dev badge. |
| frontend/src/components/ErrorBoundary.tsx (new) | Recoverable fallback for render failures. |
| frontend/src/components/ActivityRow.tsx (new) | Reusable readable event summary, time and expandable detail. |
| frontend/src/screens/HomeScreen.tsx | Truthful protection dashboard, modes, counters, activity and working shortcuts. |
| frontend/src/screens/CheckScreen.tsx | Clear decisions/local overrides, working review actions and independent catalog/detector failures. |
| frontend/src/screens/HistoryScreen.tsx | Activity filters, compact rows and empty states. |
| frontend/src/screens/SettingsScreen.tsx | Grouped settings, System option and actual navigation. |
| frontend/src/screens/SitesScreen.tsx | Rules terminology and accurate online/manual removal explanation. |
| frontend/__tests__/App.test.tsx | Matching bridge fixture and stale/missing native bridge regressions. |
| frontend/__tests__/ManualFlow.test.tsx | Snapshot/native error regressions, Continue once, scope-preserving overrides and catalog outage behavior. |
| frontend/__tests__/Screens.test.tsx | Dashboard/activity/settings state and action assertions. |
| frontend/__tests__/Theme.test.tsx | System preference, persistence and theme fixtures. |
| frontend/__tests__/ErrorBoundary.test.tsx (new) | Verify readable render recovery and retry. |
| frontend/tests/device/DnsProbe.java (new) | Reproducible real-device DNS response/system-resolver probe. |
| frontend/README.md | Current toolchain, controls, USB setup, native rebuild and saved APK instructions. |
| frontend/docs/DEVELOPMENT_WORKFLOW.md | Document bundled Dev preview and actual signing/data separation. |
| frontend/docs/ANDROID_REPAIR_REPORT.md (new) | Architecture, root causes, complete source change list and verification record. |
| backend/docs/ml/ML_INTEGRATION.md | Link newer device results without rewriting the historical integration record. |

Backend and ML source were already integrated in the existing project and did not need additional edits in this repair. Android database schema, credentials, Gradle signing keystore bytes, package dependencies and authentication/business routes were preserved.

## Automated verification

Commands run from frontend unless otherwise stated. On Windows, JAVA_HOME was set to C:\Program Files\Java\jdk-21 and ANDROID_HOME to the user's installed Android SDK.

```powershell
npm.cmd test -- --runInBand --silent
npm.cmd run typecheck
npm.cmd run lint
cd android
.\gradlew.bat :app:assembleDevelopmentDebug :app:testDevelopmentDebugUnitTest :app:assembleDevelopmentRelease -PreactNativeArchitectures=arm64-v8a --max-workers=2 --console=plain
# From backend:
.venv\Scripts\python.exe -m pytest -q
```

| Check | Result |
| --- | --- |
| Frontend | 9 suites, 116 tests passed; typecheck and lint exit 0. |
| Native | Gradle build successful; JUnit wrapper passed 23 core scenarios, including 5,000 malformed DNS packets. |
| Backend | 107 passed, 1 PostgreSQL integration test skipped by its environment gate. |
| Frozen ML/data | 19 checked hashes unchanged. |
| APK | Development debug and bundled development release built successfully for the connected arm64 phone. |

The native tests cover normalization, exact/subdomain precedence, DNS responses and service state rules. React tests cover invalid/missing native contracts, malformed snapshots, action failures, warning navigation/overrides, System preference and independent detector/catalog outcomes. Build/test logs are retained in ignored verification/.

## Physical verification

- Reinstalled matching Dev APKs using adb install -r; native calls worked without the two reported errors. Existing stable installation was preserved.
- Online DNS tested Stake/www Stake/Wikipedia/Microsoft; override mutations changed real DNS responses, and Activity recorded decisions.
- Manual mode tested twice with adb reverse tcp:8000 removed: Facebook NXDOMAIN, Wikipedia normal answers; ON -> OFF -> ON -> OFF succeeded. The VPN service was absent after Stop.
- Online outage tested with the backend mapping removed: Wikipedia returned SERVFAIL (rcode 2, zero answers), UI changed to ERROR, then Stop returned OFF. Mapping was restored.
- Continue once opened Chrome; Go back returned Home. No persistent Microsoft override remained. Appearance preference/rule persistence were checked after cold launch.
- Additional control checks and bundled APK verification are recorded in the completion note below. Clear-history testing uses Cancel to preserve device history; its confirmed mutation is covered by the existing action tests.

Completion checks: Android app settings opened the actual InstalledAppDetails page. Clear local history opened its confirmation and Cancel retained history. All five Activity filters responded; Blocked and Warnings displayed actual events, warning rows said WARNING · ALLOWED, and event details expanded. The bundled developmentRelease APK was installed over Dev, launched successfully with the Metro port mapping removed, retained the saved Facebook rule and correctly displayed the unconfigured online service. Its real manual DNS tests returned Facebook NXDOMAIN and Wikipedia answers; Stop returned OFF. The original stable Room rule rows were compared with the pre-test backup and were unchanged. The matching debug APK was then restored for continued USB online testing; the independently runnable bundled APK remains in Download.

## Saved app and mobile use

The saved, bundled artifact is frontend/build/BetGuard-Preview-2026-10-05.apk, copied to the phone's Download folder. It has the com.betguard.dev identity, uses the existing local development signing key and targets arm64. It runs without Metro. This is a testing APK, not a store-signed release.

SHA-256: `4eb25025c88caf58ff73b528d7221c1ce9780cadcc32d794097c6381bb93b1e1`.

The current release configuration has an empty remoteBaseUrl. Therefore this saved APK supports offline manual protection; its online controls correctly report an unconfigured service. Set an actual deployed HTTPS FastAPI URL in frontend/api.config.json and rebuild for online detection away from USB. No deployment endpoint was supplied or invented.

USB debug testing uses the existing FastAPI at 127.0.0.1:8000 and Metro at 8081, with adb reverse for both ports. After reconnecting, restore both mappings and open BetGuard Dev. Native changes require rebuilding/reinstalling; JS-only debug changes can reload through Metro.

## Remaining limits

- The older BetGuard app cannot be updated in place with either provided debug key. Its original signing identity is needed; replacing it by uninstalling would erase its separate data.
- The reviewed catalog endpoint returned 503 on this machine; database health is not certified. The independent finalized detector responded normally. A gated database integration test was skipped, not treated as passed.
- This VPN routes IPv4 UDP DNS through 10.77.0.2:53. DNS over HTTPS/private DNS, external resolvers, TCP DNS, direct IP access, cached answers and established connections can bypass it. IPv6-only/captive-portal handling is not certified. A blocked DNS result does not guarantee every browser connection is blocked.
- VPN permission cancellation/revocation and rare OS/process failures are guarded in code and core/UI tests; exhaustive OS/device/network testing remains outstanding. Protection requires re-enabling after process termination or reboot.
- Activity retains only 200 events; daily counters are descriptive counts of retained requests, not complete visit statistics.
- iOS filtering is not implemented. Only the connected Android 13 arm64 phone was physically verified.
- Build warnings remain for existing deprecated Android APIs, Gradle features and the React Native FeatureFlags export fallback. They did not prevent tested builds; no speculative package upgrade was made.
