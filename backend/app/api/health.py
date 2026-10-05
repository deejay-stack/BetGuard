from fastapi import APIRouter, Request
from sqlalchemy import select, text
from app.core.database import REVISION, SCHEMA
from app.models import DomainCatalog
from app.api.errors import unavailable

router = APIRouter()


@router.get("/health/live")
def health():
    return {"status": "ok"}


@router.get("/health/detection", responses={503: {"description": "Detection unavailable"}})
def detection_readiness(request: Request):
    # Component readiness in the existing health router; database readiness and
    # its original response contract are preserved.
    runtime = getattr(request.app.state, "betguard_runtime", None)
    if runtime is None:
        return unavailable("detection_unavailable")
    return runtime.get_status()


@router.get("/health/ready", responses={503: {"description": "Database or migration unavailable"}})
def readiness(request: Request):
    engine = request.app.state.engine
    if engine is None:
        return unavailable()
    with engine.connect() as connection:
        revisions = connection.execute(text(f"SELECT version_num FROM {SCHEMA}.alembic_version")).scalars().all()
        if revisions != [REVISION]:
            return unavailable()
        # Exercises actual table/column access under the application role.
        connection.execute(select(DomainCatalog).limit(1)).first()
    return {"status": "ready", "model": request.app.state.model.status}


