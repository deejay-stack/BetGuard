from fastapi import APIRouter, Depends

from app.schemas.domain import (DomainBatchRequest, DomainBatchResponse,
                                DomainCheckRequest, DomainCheckResponse)
from app.services.domain_service import evaluate, get_betguard_runtime, get_svm_shadow

router = APIRouter(prefix="/v1/domain", tags=["domain detection"])


@router.post("/check", response_model=DomainCheckResponse,
             responses={503: {"description": "Detection unavailable"}})
def check_domain(payload: DomainCheckRequest, runtime=Depends(get_betguard_runtime), shadow=Depends(get_svm_shadow)):
    result = evaluate(runtime, [payload.domain], shadow=shadow)[0]
    return DomainCheckResponse(result=result)


@router.post("/check-batch", response_model=DomainBatchResponse,
             responses={503: {"description": "Detection unavailable"}})
def check_batch(payload: DomainBatchRequest, runtime=Depends(get_betguard_runtime), shadow=Depends(get_svm_shadow)):
    results = evaluate(runtime, payload.domains, batch=True, shadow=shadow)
    return DomainBatchResponse(count=len(results), results=results)
