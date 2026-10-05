"""Retired standalone server. Detection now runs in the existing FastAPI app.

From backend: .venv/Scripts/python -m uvicorn app.main:app --port 8000
Routes: POST /v1/domain/check and POST /v1/domain/check-batch.
"""

if __name__ == "__main__":
    raise SystemExit("Use backend app.main:app; see backend/README.md.")
