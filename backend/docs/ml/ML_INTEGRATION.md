# BetGuard domain detection integration

The integration record below describes the original implementation. Subsequent Android bridge, UI, build and physical-device verification is documented in [Android repair report](../../../frontend/docs/ANDROID_REPAIR_REPORT.md); that report supersedes the earlier device/build limitations. The trained model, datasets and runtime policy are unchanged.

## Architecture discovered

The repository root is `betguard/`, with `backend/`, `frontend/`, and `ml/`.
`backend/app/main.py` owns the single FastAPI application and its async lifespan.
Routes live in `app/api/`, Pydantic schemas in `app/schemas/`, and services in
`app/services/`. The established API uses `/v1`; it has no user authentication
dependency, and the mobile UI explicitly requires no account. No authentication
or middleware was removed or bypassed.

SQLAlchemy/psycopg and Alembic access the private Supabase PostgreSQL reviewed
domain catalog using the existing configuration. `/v1/check` preserves its
reviewed-catalog priority, including reviewed unknown, and optional legacy model
service. Database startup, migrations, credentials and catalog data are unchanged.

React Native's API client is `frontend/src/api/client.ts`, configured by
`src/api/config.ts` and `api.config.json`. Android's `BetGuardVpnService.kt`
filters its virtual IPv4 UDP DNS resolver. Manual rules and the latest 200 history
events live in Room through `RuleRepository.kt`; they are not server database
records. The most specific matching manual rule retains precedence and its exact
hostname/subdomain scope. iOS filtering remains unimplemented.

The existing detector is `ml/src/runtime_service.py`, delegating to
`decision_engine.py`. Its baseline artifact is
`ml/models/baseline_domain_classifier.joblib`; selection metadata is
`ml/models/deployment_candidate.json`, and its verified list is
`ml/data/runtime/gambling_blocklist.csv` (359,736 unique domains at verification).

## Integration flow

```text
Explicit Check Link
  -> native hostname normalization/local rule lookup
  -> existing React Native HTTP client
  -> /v1/check (existing catalog) + /v1/domain/check (detection)
  -> process-wide BetGuardRuntime
  -> verified blocklist / unchanged baseline model / existing prediction cache
  -> ALLOW / WARN / BLOCK shown using existing Badge, Text and Notice

Android DNS request, with online detection explicitly enabled
  -> existing Room rule lookup (local overrides win)
  -> unmatched hostname to /v1/domain/check on a non-VPN network
  -> the same process-wide BetGuardRuntime
  -> BLOCK: existing NXDOMAIN response and local blocked history/counter
  -> WARN: existing DNS forwarding plus uncertain warning in local History
  -> ALLOW: existing DNS forwarding
  -> unavailable: SERVFAIL, local error history, degraded protection status
```

Manual mode never depends on the backend. Starting online mode is an explicit
choice in the existing enable dialog, which discloses hostname transmission and
error behavior. Decisions do not create manual rules. A manual Allow saved while
HTTP is pending takes precedence over a detection Block; a newly saved manual
Block takes precedence over a pending warning or upstream response.

Runtime startup loads finalized artifacts only. Warning threshold remains
`0.512117`, and automatic ML block policy remains `0.70`; the latter is a
conservative policy, not a statistically calibrated threshold. Model scores are
not guarantees. No model, selection metadata, training dataset, external holdout,
feature engineering, threshold calibration or offline evaluation was changed.

## Files changed

Paths are relative to `betguard/`.

| File | Reason |
| --- | --- |
| `README.md` | Describe the existing finalized ML directory and integration setup. |
| `backend/README.md` | Runtime installation, routes, deployment and retained catalog behavior. |
| `backend/.env.example` | Document optional portable artifact-root configuration. |
| `backend/app/main.py` | Load the runtime once in the existing lifespan; preserve cleanup and register detection routes. |
| `backend/app/api/health.py` | Add detection component readiness in the existing health router; retain existing health contracts. |
| `backend/tests/test_backend.py` | Isolate existing catalog tests from real ML startup. |
| `backend/tests/test_model_service.py` | Isolate existing legacy model tests from real ML startup. |
| `ml/src/decision_engine.py` | Central module-relative resources and portable manifest separators; use the bundled public suffix snapshot without network/disk cache. Policy is unchanged. |
| `ml/src/runtime_service.py` | Support package/CLI imports; disable shared text lists for app use; make inference/cache insertion atomic with reload. |
| `ml/src/api_service.py` | Retire the obsolete Flask development server and direct callers to the existing FastAPI startup. |
| `frontend/src/api/client.ts` | Extend the existing client with domain and batch request shapes/routes. |
| `frontend/specs/NativeBetGuard.ts` | Expose detection mode configuration through the existing native bridge. |
| `frontend/src/state/BetGuardContext.tsx` | Pass the existing public API address when the user selects online detection; retain manual mode. |
| `frontend/src/screens/CheckScreen.tsx` | Display independent detection decisions with existing components; retain catalog and manual controls. |
| `frontend/src/screens/HomeScreen.tsx` | Extend the existing enable confirmation and count actual detection blocks. |
| `frontend/src/screens/HistoryScreen.tsx` | Label detection blocks and allowed warnings in the existing history cards. |
| `frontend/src/screens/SettingsScreen.tsx` | Disclose optional online detection and its privacy/error behavior. |
| `frontend/android/app/src/main/java/com/betguard/filter/RuleRepository.kt` | Store the current process's selected detection endpoint; retain Room rules/history unchanged. |
| `frontend/android/app/src/main/java/com/betguard/filter/BetGuardModule.kt` | Implement detection configuration in the existing bridge. |
| `frontend/android/app/src/main/java/com/betguard/filter/BetGuardVpnService.kt` | Ask the runtime for unmatched domains in online mode and apply decisions through existing DNS handling. |
| `frontend/android/app/src/main/java/com/betguard/filter/core/DnsDecision.kt` | Preserve manual override priority and keep WARN responses allowed. |
| `frontend/__tests__/ManualFlow.test.tsx` | Regression tests for online/manual selection and uncertain warning UI without saved block rules. |
| `frontend/tests/native/CoreTests.kt` | Test WARN forwarding, detection NXDOMAIN and manual override precedence. |
| `frontend/README.md` | Document optional DNS classification, hostname privacy and native rebuild requirements. |

## Files created

| File | Purpose |
| --- | --- |
| `ml/pyproject.toml` | Install the existing source as `betguard_runtime`; record compatible runtime dependencies from the artifact environment. |
| `ml/src/__init__.py` | Make the runtime importable without changing `sys.path`. |
| `ml/src/runtime_paths.py` | Resolve resources centrally; support `BETGUARD_ML_ROOT` for deployed artifact trees. |
| `backend/app/services/domain_service.py` | Lifecycle loader, app-state dependency and logged private 503 error handling. |
| `backend/app/schemas/domain.py` | Strict request, bounded batch and meaningful decision response models. |
| `backend/app/api/domain.py` | Thin `/v1/domain/check` and `/v1/domain/check-batch` routes using the existing runtime. |
| `backend/tests/test_domain_detection.py` | Real-artifact API, lifecycle, cache, normalization, priority, concurrency and error integration tests. |
| `frontend/src/api/domain.ts` | Typed response validation using the existing client; single and batch detection calls. |
| `frontend/__tests__/Domain.test.ts` | API validation, warning semantics, normalization, errors and batch bounds. |
| `frontend/android/app/src/main/java/com/betguard/filter/DetectionClient.kt` | Native adapter for the same API when the VPN runs without JavaScript; bounded timeouts/body and non-VPN resolution. |
| `backend/docs/ml/ML_INTEGRATION.md` | This implementation report and verification guide. |

## Verification

Before edits: backend `python -m pytest -q` passed 84 tests with one guarded
PostgreSQL integration test skipped; frontend `npm.cmd test -- --runInBand`
passed all 96 tests. FastAPI started with its real environment and returned 200
for `/health/live`; the existing catalog and health routes appeared in OpenAPI.

After integration, from `backend/`:

```powershell
.venv\Scripts\python -m pip install -e ../ml
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pip check
```

The runtime was installed with the existing matching sklearn/numpy/joblib/
tldextract versions plus missing pandas dependencies. No existing dependency was
upgraded. The tests exercise real finalized artifacts and do not write fixtures
to the real database or datasets. The guarded PostgreSQL test requires a separate
explicitly confirmed test database; it remains skipped here.

From `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test -- --runInBand --testTimeout=20000
```

Type checking and linting passed; 108 frontend tests passed across eight suites.
The final backend suite passed 107 tests with one guarded PostgreSQL test skipped;
`python -m pytest -q tests/test_domain_detection.py` separately passed all 23
integration tests, including the reload race. `pip check` found no broken
requirements. Python compilation passed, and `python -m alembic history` reported
the unchanged `0001_catalog` head. Existing FastAPI/Starlette test-client
deprecation warnings remain.

Uvicorn was also started on loopback port 8001 for live HTTP verification using
the actual environment. `/health/live`, `/health/detection`, OpenAPI, and the
batch endpoint succeeded. The blocklist loaded 359,736 domains. The results were:

| Domain | Enforcement | Intervention | Source | ML score |
| --- | --- | --- | --- | --- |
| `stake.com` | BLOCK | BLOCK | verified_gambling_blocklist | null |
| `wikipedia.org` | ALLOW | NONE | ml_low_risk | 0.203321 |
| `microsoft.com` | ALLOW | WARN | ml_warning | 0.583148 |

Repeated normalized checks shared cache entries. Missing/corrupt artifacts,
inference exceptions and malformed decisions returned 503 while process health
remained available. Existing catalog priority, database failure behavior, health
contracts and response privacy continued to pass their regression tests.
Live `/health/ready` and `/v1/check` returned the existing 503 unavailable response
with the current private environment. No claim of a successful remote database
connection is made. SHA-256 comparisons confirmed every inspected model artifact,
processed training dataset/split and frozen external holdout stayed unchanged.

Android verification compiled all app Kotlin/Java, generated the updated native
bridge and Room code, and passed `:app:testDevelopmentDebugUnitTest`. That JUnit
test passed all 23 native core regression scenarios, including WARN forwarding,
NXDOMAIN only for BLOCK, late manual overrides and 5,000 malformed DNS samples.

The normal configured build could not run because SDK 37/build-tools 37/NDK 27.1
are absent, and SDK manager could not find `platforms;android-37`. Verification
therefore used a temporary Gradle init script selecting installed SDK 36,
build-tools 36.1.0 and NDK 27.3.13750724. Project build files were not modified.
Offline mode initially lacked Maven dependencies; allowing Gradle to download
them completed the native compilation and tests successfully. This verifies
source/bridge compilation and core behavior, not the configured SDK 37 APK or a
physical-device VPN session. Existing third-party/Android deprecation warnings
remain.

The command was run from `frontend/android/`, with a valid JDK root in JAVA_HOME
and the installed SDK root in ANDROID_HOME:

```powershell
$taskInit = Join-Path $env:TEMP 'betguard-verify-android.gradle'
.\gradlew.bat :app:testDevelopmentDebugUnitTest -I $taskInit
```

The temporary script contained:

```groovy
gradle.beforeProject { p ->
    ['com.android.application', 'com.android.library'].each { plugin ->
        p.plugins.withId(plugin) {
            def a = p.extensions.getByName('android')
            a.ndkVersion = '27.3.13750724'
            a.ndkPath = System.getenv('ANDROID_HOME') + '/ndk/27.3.13750724'
        }
    }
    p.afterEvaluate {
        def a = p.extensions.findByName('android')
        if (a != null) {
            a.compileSdk = 36
            a.buildToolsVersion = '36.1.0'
            a.ndkVersion = '27.3.13750724'
            a.ndkPath = System.getenv('ANDROID_HOME') + '/ndk/27.3.13750724'
        }
    }
}
```

## How to test

From the workspace root in PowerShell:

```powershell
cd betguard/backend
.venv\Scripts\python -m pip install -e ../ml
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/detection
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/domain/check -ContentType 'application/json' -Body '{"domain":"stake.com"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/domain/check-batch -ContentType 'application/json' -Body '{"domains":["stake.com","wikipedia.org","microsoft.com"]}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/domain/check -ContentType 'application/json' -Body '{"domain":"https://www.stake.com/casino"}'
```

The last request normalizes to `stake.com` and should use the existing cache.
OpenAPI is at `http://127.0.0.1:8000/docs`. Detection works independently of the
database; `/health/ready` and `/v1/check` still require database availability.

For USB Android development, retain `developmentTarget: "device"` in the existing
`frontend/api.config.json`, use `adb reverse tcp:8000 tcp:8000` and
`adb reverse tcp:8081 tcp:8081`, start Metro from `frontend/`, and rebuild the
native APK using the project's normal Android workflow. In Check Link, inspect
all three domains. In Home, select online detection, trigger fresh supported DNS
requests, and inspect History. Save an Allow for a blocked domain and verify it
overrides detection; save a Block and verify it still works with FastAPI stopped
in manual mode. Verify online service failure reports a resolution error and
degraded state. WARN must never be counted as a policy block.

## Remaining limitations

- Physical-device routing, USB loopback on a bound non-VPN network, lifecycle,
  notifications and Room persistence still require the Android acceptance checks.
  Unit tests do not establish physical VPN correctness.
- Detection warnings use the existing Check Link Notice and History cards. There
  is no browser overlay or confirmation screen that intercepts other apps.
- Manual rules remain in Room and are enforced locally; there are no user list
  database records to synchronize. Shared server text lists are disabled. If
  accounts are added later, implement scoped overrides without mutating a shared
  runtime or sharing cached user decisions (future TODO).
- Blocklist refresh remains the separate offline `ml/src/update_runtime_blocklist.py`
  maintenance command. No scheduler was added. Restart workers after refreshing
  local artifacts; each worker has its own model, blocklist and bounded cache.
- IPv4 UDP DNS through the virtual resolver is the existing enforcement scope;
  encrypted DNS, TCP DNS, direct IPs, cached answers and existing connections can
  bypass it. iOS filtering remains unsupported.
- Production requires the configured HTTPS API URL, trusted packaged artifacts
  and matching runtime dependencies. A wheel install needs `BETGUARD_ML_ROOT`.
- No remote database migration or data import was performed. PostgreSQL behavior
  beyond isolated software tests needs the existing guarded integration workflow.
- The configured Android SDK 37/build-tools 37/NDK 27.1 are absent on this machine;
  SDK manager could not find `platforms;android-37`. Project toolchain settings were
  not changed. Native validation attempts and their outcome are recorded below.
