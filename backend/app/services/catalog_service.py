"""Read reviewed labels first; model predictions never modify the catalog."""
from sqlalchemy.orm import Session
from app.models import DomainCatalog
from app.schemas.catalog import CheckResponse


def classify(hostname: str, entry) -> CheckResponse:
    if entry is None:
        return CheckResponse(hostname=hostname, classification="unknown", reason="not_in_catalog")
    if entry.review_status != "reviewed" or entry.reviewed_at is None:
        return CheckResponse(hostname=hostname, classification="unknown", reason="not_reviewed")
    return CheckResponse(
        hostname=hostname, classification=entry.classification, reason="reviewed_catalog",
        source="reviewed_catalog", explanation=(
            "This reviewed entry remains ambiguous or has insufficient information."
            if entry.classification == "unknown" else
            "Classification from a reviewed catalog entry; this does not establish website safety."
        ),
        label_provenance=entry.label_provenance, reviewed_at=entry.reviewed_at,
    )


def check_website(hostname, engine, service):
    with Session(engine) as session:
        entry = session.get(DomainCatalog, hostname)
        result = classify(hostname, entry)
    # Reviewed unknown is a deliberate hold and must not be overridden.
    if result.source == "reviewed_catalog":
        return result
    prediction = service.predict(hostname)
    if prediction is None:
        explanation = "No validated model is configured." if service.status == "absent" else "The configured model is unsuitable and was not loaded."
        return result.model_copy(update={"explanation": (
            "This hostname has no reviewed definitive catalog label. " + explanation + " Classification remains unknown."
        )})
    return CheckResponse(hostname=hostname, source="model", model_version=service.version,
                         **prediction, explanation={
                             "model_prediction": "A hostname-based model produced this classification. It may be wrong and does not establish website safety.",
                             "model_abstained": "The model's score falls in its abstention region. There is insufficient evidence for a definitive classification.",
                             "model_ineligible": "This hostname is outside the model's supported public-suffix domain format.",
                         }[prediction["reason"]])
