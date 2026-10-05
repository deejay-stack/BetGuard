# Supabase PostgreSQL milestone

The newer [ML milestone](../ml/ML_PIPELINE.md) extends the existing checker with optional validated-model inference. The connection, migration, role and USB setup below still applies. Missing/pending catalog entries can use that model; reviewed unknown remains a hold. No real-data model is currently bundled. Consult the ML guide for the current source/unknown/error response contract.

React Native → FastAPI → SQLAlchemy (psycopg 3) → Supabase PostgreSQL. Alembic owns the backend schema. Android Room/SQLite remains the permanent store for manual rules and the latest 200 history events. A catalog result never saves a rule or changes VPN policy. No Supabase SDK, API key, Auth, Storage, Realtime or Edge Functions are used.

## 1. Prepare your Supabase project

Create or select the intended project. Keep a separate project for synthetic tests. Before changing an existing project, take a backup/snapshot appropriate to your plan and inspect its tables using the command below. Do not reset the database, recreate existing tables in the dashboard, or import demonstration labels into your real catalog.

In the project's **Connect** dialog, copy the PostgreSQL connection string for the selected method. Copy the exact hostname, username and port; do not infer the pooler hostname from the region. The database password is the PostgreSQL role password, not a Supabase API key.

| Purpose | Recommended connection |
| --- | --- |
| Persistent FastAPI on an IPv6-capable host, or project with direct IPv4 support | Direct PostgreSQL, port 5432, with SQLAlchemy's small local pool |
| Persistent FastAPI on an IPv4-only Windows/network/deployment host | Shared **Session pooler**, port 5432 |
| Alembic and imports | Direct connection with a schema-owner role; Session pooler on 5432 is the IPv4 fallback |

The deployment host's IP support is not known yet. For this Windows USB development setup, start with the Session pooler unless you have verified direct IPv6 reachability. Transaction pooling on 6543 is intentionally rejected by this configuration; this persistent service does not need it. App and migration URLs can use different connection methods but must point to the same project/database. These choices follow [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres) and [SQLAlchemy guidance](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT).

In **Database settings**, enable SSL enforcement and download the server CA certificate. Prefer `sslmode=verify-full` and set the absolute certificate path. `sslmode=require` is also accepted: it requires encryption but does not guarantee server identity verification. Never use `disable`, `allow`, or `prefer`. See [Supabase SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement).

## 2. Configure the backend privately

From `betguard` in PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock.txt
.venv\Scripts\python -m pip install --no-deps -e .
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `backend/.env` locally, or use your deployment's secret environment settings. Real environment variables take precedence over `.env`. The committed template has deliberately unusable placeholders.

Supply these exact values privately:

- `DATABASE_URL`: your application-role PostgreSQL URI, using `postgresql+psycopg://`, the actual host, user, port, database, percent-encoded password, and `?sslmode=verify-full`.
- `MIGRATION_DATABASE_URL`: your schema-owner URI for the same project, generally the dashboard's `postgres` connection. It falls back to `DATABASE_URL` when omitted; separate roles/URLs are recommended.
- `DATABASE_SSL_ROOT_CERT`: the absolute path to the downloaded CA certificate. Use forward slashes in Windows dotenv paths, for example a real path under your user folder. Set `MIGRATION_DATABASE_SSL_ROOT_CERT` only if that connection needs a different CA file.

For direct connections the user is a PostgreSQL role name. With the shared pooler it is `<ROLE>.<PROJECT_REF>`. Preserve the dashboard's username format. Encode special password characters such as `@`, `:`, `/`, `%`, `#` and `?` as URL components; do not encode the whole URL. Never paste passwords or complete connection strings into chat, shell command arguments, screenshots or source control.

The `.env` files and certificate files are ignored by Git. No database URL belongs in `frontend/api.config.json` or any mobile asset. Connection parsing, SQL failures, and validation responses suppress credentials, SQL details and submitted URLs. SQL echo is disabled; keep driver debug logs and request-body logging disabled in deployment too.

The application uses 3 connections per worker with no overflow, a 5-second pool wait/connect timeout, 5-second statement/lock timeouts, and connection health checks. Budget the total across all worker processes against the project's connection limit. Migrations use `NullPool`.

## 3. Inspect and migrate

With the owner migration URL configured, run from `backend`:

```powershell
.venv\Scripts\python -m app.cli inspect-db
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m alembic current
.venv\Scripts\python -m app.cli inspect-db
```

`inspect-db` is read-only. It lists table/column names, catalog ownership, RLS flags, visible grants and current-role privilege flags; it does not print catalog rows or credentials. Review any existing catalog-like tables before upgrading. It cannot identify a legacy catalog with an arbitrary name for you.

Alembic also inspects existing tables before making changes. An unmanaged `domain_catalog`, including one in another schema, blocks the migration. Stop and create a reviewed reconciliation migration for that actual schema; do not stamp it as current, drop it, or copy a second empty schema over it. An existing `betguard_reader` role also causes the initial migration to roll back, because its privileges and memberships must be reviewed before reuse. No hosted schema was available for inspection during this implementation.

The initial migration creates `betguard_private.domain_catalog` and an Alembic version table in that private schema. Hostname is the unique primary key. Labels are `gambling`, `non_gambling`, or `unknown`; provenance is mandatory. Review status is `pending` or `reviewed`, and a reviewed row requires a timezone-aware review timestamp at import. Creation/update timestamps are server generated, with a trigger maintaining updates. No seed data is inserted. Destructive downgrade is deliberately disabled; use reviewed forward migrations. Repeat `upgrade head` applies only unapplied revisions.

Future `alembic revision --autogenerate -m "description"` comparisons are restricted to this catalog, excluding unrelated/Supabase-managed schemas and tables. Review generated migrations before applying them; autogenerate does not manage the custom grants, policies or timestamp trigger for you.

## 4. Application role and Data API boundaries

Keep `betguard_private` **out of the Data API's exposed schemas**. Since this milestone does not use the Data API, disable it for a dedicated BetGuard project if it is not needed by another application. Do not change unrelated applications' schemas or API settings. See [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api).

The migration revokes schema/table access from `PUBLIC`, `anon`, `authenticated`, and `service_role` where present. It revokes the migration owner's automatic future table/function grants within this schema. RLS is enabled on both tables. Only the `betguard_reader` group gets explicit SELECT policies and grants for the catalog and migration version; no mobile access policy exists. Review defaults again if a different owner starts creating objects.

After migrating, provision a dedicated application **LOGIN** role using your private database administration tools. It must have `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOBYPASSRLS`, and `INHERIT`; grant it membership in `betguard_reader` and database CONNECT. Set its strong password privately. This is role administration, not manual table creation. For a chosen login named `betguard_app`, the non-secret role setup is:

```sql
CREATE ROLE betguard_app LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT CONNECT ON DATABASE postgres TO betguard_app;
GRANT betguard_reader TO betguard_app;
```

Then use the interactive psql `\password betguard_app` command or a secure role-management interface to set the password without placing it in a SQL script. Replace the role/database names if your project uses different ones. Configure `DATABASE_URL` with this login; keep the owner's connection only in `MIGRATION_DATABASE_URL`. The API role cannot import, update or delete catalog entries.

RLS does **not** constrain a superuser, `BYPASSRLS` role, or ordinarily the table owner. A privileged `postgres` migration connection can read/write the catalog through ownership/privileges; that is the intended administrative path. This is a backend-owned shared catalog, not per-user data secured by Supabase Auth. The FastAPI process never uses a Supabase service-role key. See [Supabase RLS behavior](https://supabase.com/docs/guides/database/postgres/row-level-security).

Run readiness with the actual application role. Inspect Data API schema exposure in the dashboard, and verify the grants using the owner inventory command. Live role/grant/RLS verification remains pending until the project is configured.

## 5. Import a reviewed catalog

Prepare a UTF-8 JSON array of objects with `hostname`, `classification`, `label_provenance`, `review_status`, and `reviewed_at`. Use a real source description and actual review date for each reviewed label. Pending rows use `reviewed_at: null`. Dates include a timezone, for example ISO 8601 with `Z`; future review dates are rejected. Do not use invented labels to populate the application database.

```powershell
.venv\Scripts\python -m app.cli import-catalog C:\private\reviewed-catalog.json --dry-run
.venv\Scripts\python -m app.cli import-catalog C:\private\reviewed-catalog.json
```

These file paths are placeholders for your real privately maintained catalog. Dry-run validates without connecting. All rows validate before writing; duplicate normalized hosts, unknown fields, invalid labels and invalid reviews reject the whole batch. Limit: 5 MB / 10,000 rows per file. Import is one transaction, with no deletes. Existing hosts reject the batch by default; add `--update-existing` only after reviewing intentional replacements. Updates preserve `created_at` and refresh `updated_at`. Import uses the migration role, never the read-only application role.

## 6. Start FastAPI and connect the Android phone

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health/ready
adb devices
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8081 tcp:8081
```

From `betguard/frontend`, run `npm.cmd start` and open/reload the Android development app. USB forwarding maps the phone's `127.0.0.1:8000` to the PC backend and 8081 to Metro. Reapply forwarding after reconnecting USB. For an Android emulator, set `developmentTarget` to `emulator` to use `http://10.0.2.2:8000`.

`frontend/api.config.json` contains public settings only: `developmentTarget` selects `device`, `emulator` or `remote`; `remoteBaseUrl` is the real deployed HTTPS FastAPI address. Device development uses localhost and emulator development uses 10.0.2.2. Preview/production use only `remoteBaseUrl`; empty means unconfigured/unavailable. Plain HTTP is accepted only for the documented development loopback/emulator addresses. The existing Android debug manifest configuration permits development cleartext; release needs HTTPS.

No new native dependency, native bridge change, or Android resource change was introduced by this milestone. A Metro reload is sufficient **if the installed debug APK already contains the existing `resolveLink` and theme native bridge methods**. The previously documented older phone APK predates those methods, so it still needs the existing native milestone rebuilt/installed. A release APK bundles JavaScript and needs a rebuild for any UI or `frontend/api.config.json` change. Backend `.env` changes require a backend process restart, not an APK rebuild.

Check Link records the existing local check, sends only its normalized hostname to FastAPI, and shows local controls even when lookup fails. Network timeout is 8 seconds including reading the body. Editing input, cancelling, leaving the tab, and unmounting invalidate requests; late results cannot overwrite a newer check. Retry performs only a new catalog lookup, not another local history event. Android filtering never waits for this API.

## API behavior and deployment scope

| Request | Success | Failure |
| --- | --- | --- |
| `GET /health/live` | 200, process alive regardless of database | Process unavailable |
| `GET /health/ready` | 200 only when current migration and catalog read succeed | 503 for missing configuration/schema, wrong revision or DB failure |
| `POST /v1/check`, JSON `{"hostname":"<HOSTNAME>"}` | 200 classification plus reason and reviewed provenance/date where applicable | 422 invalid input; 503 unavailable with `Retry-After: 5` |

Lookup matches the exact normalized hostname; there is no implied parent-domain classification or website fetching. Reviewed catalog rows take precedence, including reviewed unknown. Missing/unreviewed rows remain unknown when no validated model is installed; a later validated model may classify eligible inputs. Database/service failures remain HTTP 503 rather than a completed unknown result. No confidence score or automatic blocking is introduced.

For local development bind to loopback as above. Deployment needs an HTTPS ingress, body-size limit, and request-rate limits. This milestone's read-only FastAPI endpoints have no user authentication; do not treat CORS or the private DB schema as API authentication. Import is CLI-only. Future work: choose backend/user authentication and authorization, then deployment abuse controls before broad public rollout; no Supabase Auth feature is introduced here.

## Verification

```powershell
# In backend; ordinary tests never connect to PostgreSQL
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pip check
.venv\Scripts\python -m alembic history
```

The optional PostgreSQL test requires `TEST_DATABASE_URL` for an **empty dedicated test project**, plus `BETGUARD_TEST_DATABASE_CONFIRMED=yes`. It rejects a recognizable match to the application project and refuses an existing BetGuard schema. Never use production or a shared project. It applies migrations twice, exercises import/update preservation and role boundaries, then rolls back schema, role and synthetic rows in one outer transaction. Normal tests use mocks and temporary files only, not SQLite or the application database.

Run the checks above for the current environment. Hosted connectivity/migrations need valid private credentials; physical-device checks are listed in [Android acceptance](../../../frontend/docs/ANDROID_ACCEPTANCE.md).

The [Android development/stable workflow](../../../frontend/docs/DEVELOPMENT_WORKFLOW.md) supersedes earlier single-APK instructions.
