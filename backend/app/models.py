from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.database import SCHEMA


class Base(DeclarativeBase):
    pass


class DomainCatalog(Base):
    __tablename__ = "domain_catalog"
    __table_args__ = (
        CheckConstraint("classification IN ('gambling', 'non_gambling', 'unknown')", name="classification_values"),
        CheckConstraint("review_status IN ('pending', 'reviewed')", name="review_status_values"),
        CheckConstraint("(review_status = 'reviewed') = (reviewed_at IS NOT NULL)", name="review_date_required"),
        CheckConstraint("length(trim(label_provenance)) > 0", name="provenance_required"),
        CheckConstraint("hostname = lower(hostname) AND length(hostname) BETWEEN 3 AND 253", name="normalized_hostname"),
        CheckConstraint("hostname ~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?([.][a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$' AND hostname !~ '[.][0-9]+$'", name="hostname_syntax"),
        {"schema": SCHEMA},
    )
    hostname: Mapped[str] = mapped_column(String(253), primary_key=True)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    label_provenance: Mapped[str] = mapped_column(String(500), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
