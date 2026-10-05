from fastapi import APIRouter, Depends

from app.schemas.domain import (DomainBatchRequest, DomainBatchResponse,
                                DomainCheckRequest, DomainCheckResponse)
from app.services.domain_service import evaluate, get_betguard_runtime

router = APIRouter(prefix="/v1/domain", tags=["domain detection"])


@router.post("/check", response_model=DomainCheckResponse,
             responses={503: {"description": "Detection unavailable"}})
def check_domain(payload: DomainCheckRequest, runtime=Depends(get_betguard_runtime)):
    result = evaluate(runtime, [payload.domain])[0]
    return DomainCheckResponse(result=result)


@router.post("/check-batch", response_model=DomainBatchResponse,
             responses={503: {"description": "Detection unavailable"}})
def check_batch(payload: DomainBatchRequest, runtime=Depends(get_betguard_runtime)):
    results = evaluate(runtime, payload.domains, batch=True)
    return DomainBatchResponse(count=len(results), results=results)
