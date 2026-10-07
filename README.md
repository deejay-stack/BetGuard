# BetGuard

The [capstone alignment audit](docs/CAPSTONE_ALIGNMENT.md) maps the supplied thesis to student network protection, app review, the existing trained domain model and remaining research evidence.

| Folder | Contents |
| --- | --- |
| [frontend](frontend/README.md) | React Native screens, Android/iOS, native filtering, mobile tests and build configuration |
| [backend](backend/README.md) | FastAPI, SQLAlchemy, Alembic, Supabase configuration, ML pipeline, models and backend tests |
| ml/ | Finalized baseline domain runtime, verified blocklist, and offline training/evaluation tools |

The phone communicates with FastAPI. FastAPI accesses Supabase PostgreSQL. Manual rules and history stay in Android Room; manual protection works without the backend.

Run mobile commands inside **frontend** and Python commands inside **backend**. Each side owns its dependencies, tests and relevant documentation. There is no root npm package.

The private database configuration remains at **backend/.env**. The finalized domain detector uses the existing **ml/models/** and **ml/data/runtime/** artifacts, loaded once in FastAPI. Install it using the backend README. The separate legacy catalog model loader still accepts reviewed exports under **backend/models/**. No training or blocklist downloading runs at application startup.

After the folder move, stop any Metro server running from the old path and restart it from frontend with:

```powershell
npm.cmd start -- --reset-cache
```

The move does not require clearing app data or changing database tables. Rebuild native outputs from frontend/android when needed; generated outputs from the old location were removed. See each folder's README for startup and verification commands.

Use the [stable/development Android workflow](frontend/docs/DEVELOPMENT_WORKFLOW.md) and [refactor audit with verification](backend/docs/REFACTOR_REPORT.md). Supabase runtime credentials stay restricted to betguard_app; administrative migrations use their separate connection.
