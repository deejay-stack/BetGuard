"""Application lifecycle and access to the existing BetGuard runtime."""
import logging

from fastapi import HTTPException, Request
from app.schemas.domain import DomainDecision

logger = logging.getLogger(__name__)


def load_runtime():
    try:
        # Lazy import keeps catalog/manual features working if ML dependencies
        # or finalized artifacts are missing. Only trusted local artifacts load.
        from betguard_runtime.runtime_service import BetGuardRuntime
        runtime = BetGuardRuntime(verbose=False, use_user_lists=False)
        logger.info("BetGuard detection ready: model=%s domains=%d",
                    runtime.model_config.get("model_name"), len(runtime.gambling_lookup))
        return runtime
    except Exception as error:
        # Exception messages can contain artifact paths. Log the error type and
        # recovery instructions without private filesystem/configuration values.
        logger.error("BetGuard detection initialization failed (%s). Install the "
                     "local ml package and check finalized artifacts/BETGUARD_ML_ROOT.",
                     type(error).__name__)
        return None


def get_betguard_runtime(request: Request):
    runtime = getattr(request.app.state, "betguard_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="BetGuard detection service is unavailable.")
    return runtime


def evaluate(runtime, domains: list[str], *, batch: bool = False):
    try:
        results = runtime.evaluate_many(domains) if batch else [runtime.evaluate(domains[0])]
        if any("error" in result for result in results):
            raise ValueError("Runtime rejected a validated hostname")
        decisions = [DomainDecision.model_validate(result) for result in results]
        for result in results:
            # Hostname only; never log URLs, credentials, or browsing histories.
            logger.debug("domain=%s enforcement=%s intervention=%s source=%s cache_hit=%s",
                         result["domain"], result["enforcement_action"], result["intervention"],
                         result["decision_source"], result.get("cache_hit", False))
        return decisions
    except Exception as error:
        logger.error("BetGuard detection evaluation failed (%s)", type(error).__name__)
        raise HTTPException(status_code=503, detail="BetGuard detection service is unavailable.") from None
