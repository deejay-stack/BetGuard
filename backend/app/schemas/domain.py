from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

from app.schemas.catalog import normalize_hostname

# Reuse the application's strict validation. Strip URL paths before inference;
# the runtime retains responsibility for domain normalization and cache keys.
Domain = Annotated[str, Field(min_length=1, max_length=2048), AfterValidator(normalize_hostname)]


class DomainCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Domain


class DomainBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domains: list[Domain] = Field(min_length=1, max_length=100)


class DomainDecision(BaseModel):
    domain: str
    enforcement_action: Literal["ALLOW", "BLOCK"]
    intervention: Literal["NONE", "WARN", "BLOCK"]
    risk_status: Literal["trusted", "user_blocked", "verified_gambling", "high", "suspicious", "low"]
    decision_source: Literal["user_allowlist", "user_blocklist", "verified_gambling_blocklist",
                             "ml_high_risk", "ml_warning", "ml_low_risk"]
    matched_domain: str | None = None
    ml_score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    cache_hit: bool = False

    @model_validator(mode="after")
    def consistent_enforcement(self):
        if (self.enforcement_action == "BLOCK") != (self.intervention == "BLOCK"):
            raise ValueError("WARN/NONE must remain allowed")
        return self


class DomainCheckResponse(BaseModel):
    ok: Literal[True] = True
    result: DomainDecision


class DomainBatchResponse(BaseModel):
    ok: Literal[True] = True
    count: int
    results: list[DomainDecision]
