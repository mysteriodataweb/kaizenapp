from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import Eligibility, check_in
from app.models.mixins import UUIDPk


class Match(UUIDPk, Base):
    """Résultat explicable du moteur : éligibilité, compatibilité et explications."""

    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_matches_user_opportunity"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint(check_in("eligibility", Eligibility), name="eligibility_valid"),
        Index("ix_matches_user_score", "user_id", "score"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    eligibility: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # Part (0..1) du poids total pour laquelle l'information était disponible.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # Détail par critère : structure riche consommée telle quelle par l'interface.
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    missing_profile_fields: Mapped[list[str]] = mapped_column(ARRAY(String(60)), nullable=False, server_default="{}")
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Inclusion dans une alerte « nouvelle opportunité » (une seule fois).
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
