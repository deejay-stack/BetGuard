# BetGuard backend

FastAPI + SQLAlchemy + Alembic with Supabase-hosted PostgreSQL. Mobile rules/history remain in Room, and manual protection is independent of this service. No Supabase API key is needed for the database connection.

| Path | Purpose |
| --- | --- |
| app/api/, app/core/ | Routes, shared configuration and SQLAlchemy engines |
| app/models.py, app/schemas/ | ORM table and request/response validation |
| app/services/ | Reviewed catalog lookup and optional model service |
| app/ml/ | Optional inference helpers only |
| ml_tools/ | Offline audit/training/evaluation/export tools; excluded from the application package |
| migrations/ | Alembic database migrations |
| tests/ | Backend and ML software tests |
| models/ | Future complete trained-model releases; only .gitkeep tracked |
| .env | Private database/model environment, ignored by Git |
| .env.example | Placeholder configuration only |
| docs/ | Supabase setup, model workflow, data audit, labels and input schema |

## Setup and run

Run Python commands from this backend directory. Follow [Supabase setup](docs/database/SUPABASE_SETUP.md) for installation, roles, encrypted connections, existing-table inspection and migrations. The existing private .env is preserved; do not overwrite it with the example.

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Process health is /health/live; database readiness is /health/ready. Hosted verification requires valid project credentials configured privately.

## Models

The finalized gambling-domain detector is the sibling `../ml` package. Install
it into this backend's environment without retraining or modifying artifacts:

```powershell
.venv\Scripts\python -m pip install -e ../ml
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

Each FastAPI process loads one `BetGuardRuntime` with the existing baseline
model, verified 359,736-domain blocklist, and bounded thread-safe cache.
Resource paths resolve relative to the installed ML source, independently of
the working directory. For a wheel deployment, set `BETGUARD_ML_ROOT` to an
absolute trusted artifact directory containing `models/` and `data/runtime/`.
Joblib artifacts must be trusted; there is no upload or runtime training API.

`POST /v1/domain/check` accepts `{"domain":"stake.com"}`.
`POST /v1/domain/check-batch` accepts `{"domains":["stake.com","wikipedia.org","microsoft.com"]}`
with at most 100 items. The response distinguishes `enforcement_action` from
`intervention`: WARN always permits traffic. Detection availability is exposed
by `/health/detection` in the existing health router. Unavailable initialization
or inference returns 503; catalog/database readiness remains unchanged.

Android's existing Room rules remain authoritative on the device. The API does
not read shared user text lists or upload rules. Standalone runtime/CLI use keeps
the original text-list behavior. Enable optional online detection from the
existing protection dialog; manual mode works without the backend.

The existing `/v1/check` reviewed-catalog contract and optional model service are
preserved separately:

Place each complete trusted export in a versioned directory under models, then set MODEL_ARTIFACT_DIR to that directory and MODEL_MANIFEST_SHA256 to its reviewed export hash in the private environment. Restart FastAPI. The existing loader expects the project workflow's model.skops and manifest.json, with matching dependencies and metadata; arbitrary pickle files are not accepted.

The backend models directory contains no model artifact. Only .gitkeep is tracked;
the separate finalized baseline artifact stays under ml/models. No placeholder
models, fake training data or automatic training runs are included.

See [ML workflow](docs/ml/ML_PIPELINE.md), [data requirements](docs/ml/ML_DATA_AUDIT.md) and [labeling policy](docs/ml/ML_LABELING_POLICY.md). Reviewed catalog entries, including reviewed unknown, take precedence. Missing/unsuitable models give unknown after a successful catalog lookup. Database/service errors remain unavailable.

## Checks

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pip check
.venv\Scripts\python -m alembic history
```

Ordinary tests use temporary fixtures; the PostgreSQL integration test requires an explicitly confirmed separate test database. Never load synthetic fixtures into the application project. Backend-only and optional ML dependency locks are kept separately because ML serving/training is optional.

See [refactor audit and verification](docs/REFACTOR_REPORT.md) and the [Android workflow](../frontend/docs/DEVELOPMENT_WORKFLOW.md).

See [domain integration report](docs/ml/ML_INTEGRATION.md) for the architecture,
file inventory, API examples, verification results and device limitations.
