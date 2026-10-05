from fastapi import APIRouter, Request
from app.api.errors import unavailable
from app.schemas.catalog import CheckRequest, CheckResponse
from app.services.catalog_service import check_website

router = APIRouter()


@router.post("/v1/check", response_model=CheckResponse, response_model_exclude_none=True,
             responses={503: {"description": "Classification unavailable"}})
def check_link(payload: CheckRequest, request: Request):
    if request.app.state.engine is None:
        return unavailable()
    return check_website(payload.hostname, request.app.state.engine, request.app.state.model)
