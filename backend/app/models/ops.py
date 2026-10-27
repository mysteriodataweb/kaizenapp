from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import IngestionStatus, check_in
from app.models.mixins import UUIDPk


class IngestionRun(UUIDPk, Base):
    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(check_in("status", IngestionStatus), name="status_valid"),
        Index("ix_ingestion_runs_source_time", "source_id", "started_at"),
    )

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL")
    )
    job_name: Mapped[str] = mapped_column(String(80), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, server_default="cron")
    dry_run: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_fetched: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    items_skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Liste d'erreurs et échantillons de validation (structure variable).
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class JobLock(UUIDPk, Base):
    """Verrou à bail (lease) : fonctionne aussi derrière un pooler en mode transaction,
    contrairement aux advisory locks de session."""

    __tablename__ = "job_locks"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    holder: Mapped[str] = mapped_column(String(100), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
