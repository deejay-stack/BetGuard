from fastapi import APIRouter, Request
from app.schemas.application import AppCheckResponse, AppMetadata

router = APIRouter()


@router.post("/v1/apps/check", response_model=AppCheckResponse, response_model_exclude_none=True)
def check_application(payload: AppMetadata, request: Request):
    # Explicit checks only. Never persist app inventory or student information.
    return request.app.state.app_metadata_model.check(payload)


@router.get("/health/apps")
def app_model_readiness(request: Request):
    model = request.app.state.app_metadata_model
    return {"ready": model.status == "available", "model": model.status,
            "model_version": model.version, "input": "application_metadata",
            "enforcement": "dns_network_only"}
