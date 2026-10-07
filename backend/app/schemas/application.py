"""Application information only; no student identity, usage or private content."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class AppMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    app_name: str = Field(min_length=1, max_length=200)
    package_name: str = Field(default="", max_length=255, pattern=r"^(?:[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)?$")
    description: str = Field(default="", max_length=6000)
    keywords: list[ShortText] = Field(default_factory=list, max_length=40)
    permissions: list[ShortText] = Field(default_factory=list, max_length=150)
    reviews: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=10)

    @field_validator("app_name")
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip():
            raise ValueError("An application name is required.")
        return value


class AppCheckResponse(BaseModel):
    classification: Literal["gambling", "non_gambling", "unknown"]
    source: Literal["app_metadata_model", "unavailable"]
    reason: str
    explanation: str
    model_version: str | None = None
    enforcement: Literal["dns_network_only"] = "dns_network_only"


def enough_metadata(value: AppMetadata) -> bool:
    # A name or permission alone cannot establish gambling content.
    return len(value.description) >= 40 or sum(len(review) for review in value.reviews) >= 40


def metadata_text(value: AppMetadata) -> str:
    # Package IDs identify leakage groups, never become predictive features.
    # Keep negations ("no wagering") rather than removing stop words blindly.
    return "\n".join([
        "name " + value.app_name,
        "description " + value.description,
        "keywords " + " ".join(sorted(set(value.keywords))),
        "permissions " + " ".join(sorted(set(value.permissions))),
        "reviews " + " ".join(value.reviews),
    ])
