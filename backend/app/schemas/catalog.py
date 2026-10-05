import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Classification = Literal["gambling", "non_gambling", "unknown"]


def normalize_hostname(value: str) -> str:
    value = value.strip()
    try:
        if not value or len(value) > 2048 or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError()
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if parsed.scheme.lower() not in {"http", "https"} or "@" in parsed.netloc or "%" in parsed.netloc:
            raise ValueError()
        parts = parsed.netloc.split(":")
        if len(parts) > 2 or (len(parts) == 2 and (not parts[1].isascii() or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 65535)):
            raise ValueError()
        host = parts[0].removesuffix(".").encode("idna").decode("ascii").lower()
        labels = host.split(".")
        if len(host) > 253 or len(labels) < 2 or labels[-1].isdigit() or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
        ):
            raise ValueError()
        return host
    except (ValueError, UnicodeError):
        raise ValueError("Enter a complete HTTP(S) hostname without credentials or an IP address.") from None


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=1, max_length=2048)

    @field_validator("hostname")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_hostname(value)


class CatalogEntry(CheckRequest):
    classification: Classification
    label_provenance: str = Field(min_length=1, max_length=500)
    review_status: Literal["pending", "reviewed"]
    reviewed_at: datetime | None = None

    @field_validator("label_provenance")
    @classmethod
    def provenance(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Label provenance is required.")
        return value.strip()

    @model_validator(mode="after")
    def review(self):
        if (self.review_status == "reviewed") != (self.reviewed_at is not None):
            raise ValueError("Only reviewed entries must have a review date.")
        if self.reviewed_at is not None and (
            self.reviewed_at.tzinfo is None or self.reviewed_at > datetime.now(timezone.utc)
        ):
            raise ValueError("Review dates must include a timezone and cannot be in the future.")
        return self


class CheckResponse(BaseModel):
    hostname: str
    classification: Classification
    source: Literal["reviewed_catalog", "model", "unavailable"] = "unavailable"
    reason: Literal["reviewed_catalog", "not_in_catalog", "not_reviewed", "model_prediction", "model_abstained", "model_ineligible"]
    explanation: str = "No reviewed classification is available."
    label_provenance: str | None = None
    reviewed_at: datetime | None = None
    model_version: str | None = None
    calibrated_probability: float | None = None
