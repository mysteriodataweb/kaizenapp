from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import FundingPreference, StudyLevel, check_in
from app.models.mixins import Timestamps, UUIDPk


class Profile(UUIDPk, Timestamps, Base):
    """Profil personnel. Les listes structurées éditées d'un bloc (expériences, projets,
    langues…) sont en JSONB validé par Pydantic ; les critères de filtrage simples sont
    des colonnes ou des tableaux typés."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("study_level IS NULL OR " + check_in("study_level", StudyLevel), name="study_level_valid"),
        CheckConstraint(
            "funding_preference IS NULL OR " + check_in("funding_preference", FundingPreference),
            name="funding_preference_valid",
        ),
        CheckConstraint(
            "internship_duration_min_months IS NULL OR internship_duration_min_months BETWEEN 0 AND 36",
            name="duration_min_range",
        ),
        CheckConstraint(
            "internship_duration_max_months IS NULL OR internship_duration_max_months BETWEEN 0 AND 36",
            name="duration_max_range",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str | None] = mapped_column(String(120))
    country_of_residence: Mapped[str | None] = mapped_column(String(2))
    nationalities: Mapped[list[str]] = mapped_column(ARRAY(String(2)), nullable=False, server_default="{}")
    headline: Mapped[str | None] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)

    study_level: Mapped[str | None] = mapped_column(String(20))
    current_degree: Mapped[str | None] = mapped_column(String(200))
    institution: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    academic_year: Mapped[str | None] = mapped_column(String(50))
    expected_graduation: Mapped[date | None] = mapped_column(Date)
    academic_results: Mapped[str | None] = mapped_column(String(300))

    skills: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, server_default="{}")
    experiences: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    projects: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    leadership: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    languages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")

    target_countries: Mapped[list[str]] = mapped_column(ARRAY(String(2)), nullable=False, server_default="{}")
    internship_fields: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False, server_default="{}")
    master_fields: Mapped[list[str]] = mapped_column(ARRAY(String(120)), nullable=False, server_default="{}")
    funding_preference: Mapped[str | None] = mapped_column(String(20))
    program_types: Mapped[list[str]] = mapped_column(ARRAY(String(30)), nullable=False, server_default="{}")
    internship_duration_min_months: Mapped[int | None] = mapped_column(Integer)
    internship_duration_max_months: Mapped[int | None] = mapped_column(Integer)
    accepts_remote: Mapped[bool | None] = mapped_column()

    # Incrémenté à chaque modification : déclenche le recalcul des scores.
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
