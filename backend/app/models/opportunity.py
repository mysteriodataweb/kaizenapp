from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    DeadlineStatus,
    FundingType,
    OpportunityType,
    PublicationStatus,
    SourceVerification,
    VerificationStatus,
    check_in,
)
from app.models.mixins import Timestamps, UUIDPk


class Source(UUIDPk, Timestamps, Base):
    """Source de collecte (un connecteur + sa configuration)."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(check_in("verification_status", SourceVerification), name="verification_valid"),
        CheckConstraint("rate_limit_seconds >= 0", name="rate_limit_positive"),
    )

    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    connector: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    terms_notes: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Configuration propre au connecteur (jetons de job boards, URL de flux…) : variable par nature.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    rate_limit_seconds: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("2"))
    max_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("200"))
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unverified")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)


class Opportunity(UUIDPk, Timestamps, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(check_in("type", OpportunityType), name="type_valid"),
        CheckConstraint(check_in("funding_type", FundingType), name="funding_type_valid"),
        CheckConstraint(check_in("deadline_status", DeadlineStatus), name="deadline_status_valid"),
        CheckConstraint(check_in("verification_status", VerificationStatus), name="verification_valid"),
        CheckConstraint(check_in("status", PublicationStatus), name="status_valid"),
        CheckConstraint("official_url <> ''", name="official_url_present"),
        CheckConstraint("(deadline_at IS NULL) = (deadline_status = 'unknown')", name="deadline_consistent"),
        # Une URL canonique est unique dans le catalogue commun, et pour chaque utilisateur parmi ses offres privées.
        Index(
            "uq_opportunities_canonical_public",
            "canonical_url",
            unique=True,
            postgresql_where=text("owner_user_id IS NULL"),
        ),
        Index(
            "uq_opportunities_owner_canonical",
            "owner_user_id",
            "canonical_url",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL"),
        ),
        Index("ix_opportunities_deadline", "deadline_at"),
        Index("ix_opportunities_type_status", "type", "status"),
        Index("ix_opportunities_first_seen", "first_seen_at"),
        Index("ix_opportunities_dedupe", "organization_norm", "title_norm"),
        Index("ix_opportunities_search", "search_vector", postgresql_using="gin"),
        Index("ix_opportunities_countries", "countries", postgresql_using="gin"),
        Index(
            "uq_opportunities_source_external",
            "primary_source_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    organization: Mapped[str] = mapped_column(String(300), nullable=False)
    title_norm: Mapped[str] = mapped_column(String(400), nullable=False)
    organization_norm: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    countries: Mapped[list[str]] = mapped_column(ARRAY(String(2)), nullable=False, server_default="{}")
    location: Mapped[str | None] = mapped_column(String(300))
    remote: Mapped[bool | None] = mapped_column(Boolean)
    fields: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False, server_default="{}")
    study_levels: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, server_default="{}")
    eligibility_criteria: Mapped[str | None] = mapped_column(Text)
    # NULL = non publié ; [] n'est pas utilisé pour éviter l'ambiguïté.
    eligible_nationalities: Mapped[list[str] | None] = mapped_column(ARRAY(String(2)))
    # [{"code": "en", "level": "B2"}] — liste variable selon les annonces.
    required_languages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    required_documents: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False, server_default="{}")
    funding_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    funding_amount: Mapped[str | None] = mapped_column(String(200))
    tuition_covered: Mapped[bool | None] = mapped_column(Boolean)
    stipend: Mapped[str | None] = mapped_column(String(200))
    benefits: Mapped[str | None] = mapped_column(Text)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    opens_at: Mapped[date | None] = mapped_column(Date)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_timezone: Mapped[str | None] = mapped_column(String(64))
    deadline_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    official_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200))
    primary_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL")
    )
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, server_default="{}")
    # NULL = catalogue commun ; sinon offre privée, ajoutée à partir d'un lien et visible de son seul auteur.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unverified")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    significant_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    significant_change_fields: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, server_default="{}")
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(organization, '') || ' ' "
            "|| coalesce(location, '') || ' ' || coalesce(description, ''))",
            persisted=True,
        ),
    )


class OpportunitySource(UUIDPk, Base):
    """Provenance : chaque site qui mentionne l'opportunité (sources alternatives conservées)."""

    __tablename__ = "opportunity_sources"
    __table_args__ = (
        UniqueConstraint("source_id", "source_url", name="uq_opportunity_sources_source_url"),
        CheckConstraint("source_url <> ''", name="source_url_present"),
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Données brutes de la source (schéma propre à chaque fournisseur).
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
