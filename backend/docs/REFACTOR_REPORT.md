# Refactor audit and verification — 24 September 2026

The audit preceded edits. Runtime imports, CLI commands, tests, native identifiers, startup/lifespan, migrations, configuration key names and documentation references were inspected. Private credential values were never printed or changed. The existing dirty Git state was preserved; no commit, branch, tag, push, database migration or cloud build was performed.

## Resulting source layout

```text
betguard/
├── .gitignore
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py                    Lifespan, errors and router assembly
│   │   ├── api/                       health.py, check.py, errors.py
│   │   ├── core/                      config.py, database.py
│   │   ├── schemas/catalog.py         Normalization and Pydantic contracts
│   │   ├── models.py                  Existing SQLAlchemy catalog model
│   │   ├── services/                  Catalog lookup and optional ModelService
│   │   └── ml/                        Inference helpers only
│   ├── ml_tools/                      Offline audit, training, evaluation, export
│   ├── migrations/versions/0001_catalog.py
│   ├── models/.gitkeep                No model artifact installed
│   ├── tests/                         Core, service, optional ML and PostgreSQL tests
│   ├── docs/database/                 Supabase setup
│   ├── docs/ml/                       ML workflow, audit, labels and schema
│   ├── .env                          Private; ignored
│   ├── .env.example                   Placeholders only
│   ├── pyproject.toml / alembic.ini
│   └── requirements*.lock.txt
└── frontend/
    ├── App.tsx / index.js
    ├── src/                           components, screens, state, api, theme.ts
    ├── specs/                         Existing TurboModule contract
    ├── android/                       Shared native implementation; two flavors
    ├── ios/                           Existing template, unchanged
    ├── __tests__/ / tests/native/
    ├── docs/                          Acceptance and development workflow
    ├── api.config.json / app.json / eas.json
    └── package.json / package-lock.json / build-tool configuration
```

The outer `.github` tooling was left intact. No empty frontend hooks/storage/navigation folders or single-class ORM package were created merely to resemble a template. Installed node_modules and the Python .venv remain local and ignored.

## Dependency map and ML classification

Current request path: `app.main -> api routes -> services.catalog_service -> models.DomainCatalog + core.database`. Configuration still loads `backend/.env`, with process environment taking precedence. `main -> services.model_service` supplies an optional service. Only an explicitly configured, validated artifact starts its bounded inference worker, which loads `app.ml`; no runtime module imports `ml_tools`.

| Audited ML-related file/group | Classification | Disposition and reason |
| --- | --- | --- |
| `app/model_service.py` | REQUIRED_NOW | Moved to `app/services/model_service.py`; main/API/tests use its absence/error contract. Retained bounded worker/trust checks rather than deleting a live dependency. |
| Model response fields and catalog/model selection previously in `app/catalog.py` and `app/main.py` | REQUIRED_NOW | Contracts moved to schemas; reviewed-first selection to catalog_service; routes kept at the same URLs. |
| `app/ml/__init__.py` | FUTURE_ML | Retained label/feature/policy constants needed by a future compatible inference artifact. |
| `app/ml/features.py` | FUTURE_ML | Retained fitted transformers and scoring; moved estimator-construction factories into ml_tools/features.py. |
| `app/ml/artifacts.py` | FUTURE_ML | Retained trusted inference loader; moved artifact creation into ml_tools/exporting.py. |
| `app/ml/data.py` | FUTURE_ML | Offline observations/audit/grouping moved to ml_tools/data.py; serving eligibility/PSL/integrity helpers isolated in app/ml/runtime.py. |
| `app/ml/protocol.py` | FUTURE_ML | Training/split/metrics logic moved to ml_tools/protocol.py; runtime abstention isolated in app/ml/runtime.py. |
| `app/ml/workflow.py`, `cli.py`, `inventory.py` | FUTURE_ML | Moved to ml_tools; useful explicit development tools, never API imports. |
| `tests/test_ml.py` | FUTURE_ML | Retained optional pipeline/loader tests; missing optional dependencies skip this module. Non-ML service tests moved into test_model_service.py. |
| `ML_PIPELINE.md`, `ML_DATA_AUDIT.md`, `ML_LABELING_POLICY.md`, `ML_OBSERVATION.schema.json` | FUTURE_ML | Moved under docs/ml; references and CLI commands updated. |
| `requirements-ml.lock.txt`, optional ML dependency group | FUTURE_ML | Retained reproducible optional tooling/inference dependencies; backend-only lock remains separate. |
| `models/` | FUTURE_ML | Inspection found no model, checkpoint or export. Added only .gitkeep; all actual artifacts ignored. |
| Python bytecode/test caches | UNUSED | Generated, reproducible, not source. Removed where permitted; protected-cache exception below. |

**No meaningful ML source file or reviewed artifact was deleted.** There was no installed model to validate, remove or replace. No real-data training/retraining or production export ran. Existing software tests exercise synthetic pipelines only in temporary test directories; those artifacts cannot be served as deployable models.

`ml_tools` is excluded from the packaged `app` by the existing setuptools package selection. The new development command is `python -m ml_tools.cli` from backend. Shared transform type names remain under app.ml; compatibility source hashes reflect the refactor. Future model exports must be reviewed against the current code; an arbitrary external pickle cannot be dropped into the service unchanged.

## Moved, renamed, split and deleted files

| Previous path | Current location |
| --- | --- |
| backend/app/config.py | backend/app/core/config.py |
| backend/app/db.py | backend/app/core/database.py (renamed) |
| backend/app/catalog.py | backend/app/schemas/catalog.py; classify moved to services/catalog_service.py |
| backend/app/model_service.py | backend/app/services/model_service.py |
| Routes and catalog orchestration in backend/app/main.py | api/health.py, api/check.py, api/errors.py and services/catalog_service.py |
| backend/app/ml/{data,protocol,workflow,inventory,cli}.py | backend/ml_tools/; shared runtime fragments separated as described above |
| Estimator factories / artifact saving | backend/ml_tools/features.py and exporting.py |
| Service/API tests previously in test_ml.py | backend/tests/test_model_service.py |
| backend/docs/ML_* | backend/docs/ml/ (four documents/schema) |
| backend/docs/SUPABASE_SETUP.md | backend/docs/database/SUPABASE_SETUP.md |

Imports were updated in API assembly, services, ORM, CLI, ML tools, tests and `migrations/env.py`. The migration revision itself is byte-for-byte unchanged. No obsolete import shims or duplicate implementations were left behind.

Deleted root `package.json` and `package-lock.json`: they contained only an unused `@supabase/supabase-js` installation, with no application imports or scripts referencing it. Its root `node_modules/` was removed too. The real frontend package/lock/dependencies remain in frontend. SQLAlchemy's direct PostgreSQL connection needs no JavaScript Supabase SDK. No other application source was deleted.

Python `__pycache__` directories under app/migrations/tests were cleaned without deleting .venv. They can regenerate when an already-running Python process reloads. `backend/.pytest_cache` is owned/protected by the Windows sandbox account; both direct deletion and a checked temporary move were denied. It remains ignored and is a filesystem-permission cleanup item, not an application dependency. No ACLs were weakened to remove it.

## Runtime and database behavior

- `/health/live` remains process health; `/health/ready` verifies the database, expected revision and catalog read access. Absent or unsuitable ML does not make a healthy database unavailable.
- `/v1/check` returns reviewed catalog classifications first, including a reviewed unknown hold. Missing/unreviewed entries remain unknown when the model is absent or unsuitable. No fabricated confidence or keyword labels were added.
- A future trusted model may predict or abstain for eligible unresolved inputs; inference is bounded in a separate process and never writes catalog labels. Missing artifact files now fail the optional preflight before spawning a worker.
- Database/service errors remain distinct HTTP 503 responses; validation remains 422. Existing source/reason/explanation fields are preserved.
- Runtime uses `DATABASE_URL` and restricted `betguard_app`; migration/import operations retain `MIGRATION_DATABASE_URL`. `DATABASE_SSL_ROOT_CERT` and TLS validation behavior are unchanged. No credentials/certificates moved to the phone.
- `betguard_private.domain_catalog`, `betguard_private.alembic_version`, betguard_reader and role policies/grants were not modified. No Supabase-managed schema was touched and no fixture records were inserted into the real database.

## Android and frontend changes

Stable/preview ID is **com.betguard**; development ID is **com.betguard.dev**. Development resources show **BetGuard Dev**; stable remains **BetGuard**. Explicit flavor IDs let EAS select the correct application. Native classes and namespace remain com.betguard; manifest component names are now explicit. Stop actions use the installed application ID; VPN/notification labels distinguish Dev. Existing explicit intents, private service, UID-scoped notification channels, Room and settings keep the installations separate. There are no provider/deep-link authority collisions in the current manifest.

Kotlin filtering algorithms, bridge spec, Room schema, manual-rule precedence, themes, screens and navigation were retained. Frontend organization remains compact; the useful addition is src/api/config.ts, separating public environment selection from HTTP/timeout/cancellation logic. Check Link now explicitly explains unconfigured service while retaining local actions.

EAS development builds developmentDebug with Metro using the existing bare React Native debug client. It does not claim an installed Expo dev-client launcher or set a flag for an absent native dependency. Preview builds a productionRelease APK; production builds a productionRelease AAB and retains autoIncrement. Existing EAS project identity, Gradle signing configuration and debug.keystore were preserved; the key's Git object hash matches the pre-existing version. Production publishing/signing still requires validation of the approved release identity; the unchanged local release template references debug signing.

API configuration is public JSON: device development uses 127.0.0.1:8000 through adb reverse; emulator development uses 10.0.2.2:8000. Remote development and both release profiles use only a configured HTTPS remoteBaseUrl. Empty remote configuration gives a clear unavailable/unconfigured message, never a fake hosted URL. Manual protection remains independent. Preview's local run command uses --no-packager.

New [DEVELOPMENT_WORKFLOW.md](../../frontend/docs/DEVELOPMENT_WORKFLOW.md) covers USB reconnection, all three EAS profiles, APK installation/signing compatibility, offline milestone use, main/develop/feature branches and example reviewed commit/tag commands. No Git-history operation was run. READMEs, Supabase setup, ML docs and Android acceptance links/commands were updated. `.env.example` keeps placeholders and optional model comments.

`.gitignore` now tracks only models/.gitkeep while excluding model contents, .pt/.pth/.onnx/.joblib/.pkl/.safetensors, Python bytecode/caches, .venv, .env, certificate/key files, node_modules, .expo, dist and build output. It intentionally does not globally ignore arbitrary .bin source assets; every model-directory payload is already ignored.

## Verification actually executed

| Check | Result and scope |
| --- | --- |
| Backend pytest after refactor | **84 passed, 1 skipped**; includes service/readiness absence, precedence, errors, loader compatibility, pipeline fixtures and import validation. |
| Python dependency consistency | `pip check` passed. |
| Python syntax/imports | 34 source files parsed; app.main/app.cli import successfully. Startup imports neither ML science libraries nor ml_tools. |
| ML absent without ML imports available | Startup, live, ready and unresolved check passed with a deliberately blocked ML import hook and mock database. |
| Alembic discovery | `0001_catalog (head)`; migration file unchanged. |
| Live Supabase before and after | Read-only verification passed as **betguard_app**, encrypted connection true, revision **0001_catalog**. |
| Live-database FastAPI contract | TestClient exercised the actual refactored app against Supabase: `/health/live` 200, `/health/ready` 200 ready/model absent, `/v1/check` 200 unknown/not_in_catalog for a reserved verification hostname. No row was imported or written. |
| Hosted migration status | Read with Alembic MigrationContext under the runtime account. No upgrade/reset/stamp or migration-env DDL was run. |
| ML CLI entry point | `python -m ml_tools.cli --help` passed; no real training command run. |
| TypeScript / ESLint | Passed. |
| Mobile Jest | **6 suites, 60 tests passed**: existing manual/theme/request tests plus development/emulator/release URL selection and no HTTP request when unconfigured. |
| Android JavaScript release bundle | Passed, 19 assets; output kept in temporary storage, not the repository. |
| React Native discovery | Three native dependencies resolved; Android root correctly points to frontend/android. |
| Metro startup | Passed on temporary loopback port 8197; `/status` returned HTTP 200 and packager-status:running. Only the verification process was stopped. Earlier PowerShell checks were inconclusive because they treated the raw byte response as text. |
| Native core compiler/runner | **20 scenarios passed**, including 5,000 malformed-packet samples; cached Kotlin 2.2.0/JBR, temporary output jar. Not a full Android app build. |
| Local Dev + preview APK build | Attempted `assembleDevelopmentDebug assembleProductionRelease`; blocked at missing NDK configuration. API 37, Build-Tools 37.0.0 and pinned NDK 27.1.12297006 are absent; AGP also reports preferred NDK 28.2.13676358. Versions were not changed. |
| Phone inventory | RMX3710 / Android API 33 connected; com.betguard is installed. New Dev flavor is not installed; no install/uninstall or VPN operation was performed. |

Backend tests retain two dependency deprecation warnings. Metro retains React Native's private-feature-flag resolution fallback and terminal-color warnings. The failed local native build also reports existing AGP legacy-DSL deprecations. None was suppressed or misreported as an APK success.

## Remaining prerequisites

Provide the pinned native toolchain or run reviewed EAS builds with the existing signing identity, then perform real coexistence, launch, USB-disconnection, notification/VPN and browser blocking acceptance. Both packages are configured, but coexistence has not yet been verified by installing both new artifacts. Android allows only one active VPN per profile even when both apps are installed.

Configure a real remote HTTPS FastAPI endpoint only after deployment; until then preview/production checks remain gracefully unconfigured. Do not paste database secrets into chat. Integrate the separately trained model later through a reviewed compatible artifact/adapter; no model or performance claim was fabricated here. A dedicated PostgreSQL fixture database remains required for the skipped write/migration integration test. Resolve the protected pytest-cache permissions from the appropriate local account if physical removal is desired.
