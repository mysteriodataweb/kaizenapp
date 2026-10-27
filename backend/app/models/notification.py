from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DigestFrequency, NotificationKind, NotificationStatus, check_in
from app.models.mixins import Timestamps, UUIDPk


class NotificationPreference(UUIDPk, Timestamps, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        CheckConstraint(check_in("digest_frequency", DigestFrequency), name="frequency_valid"),
        CheckConstraint("min_score BETWEEN 0 AND 100", name="min_score_range"),
        CheckConstraint("max_items BETWEEN 1 AND 50", name="max_items_range"),
        CheckConstraint("digest_weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("digest_hour BETWEEN 0 AND 23", name="hour_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    email: Mapped[str | None] = mapped_column(String(320))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    digest_frequency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="weekly")
    digest_weekday: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    digest_hour: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("8"))
    notify_new_matches: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_deadlines: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_tasks: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_changes: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_ingestion_errors: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    min_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    max_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    deadline_reminder_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default="{14,7,3,1}"
    )
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationLog(UUIDPk, Base):
    """Journal d'envoi. (user_id, dedup_key) unique : une notification logique n'est jamais
    envoyée deux fois, même si un job est relancé."""

    __tablename__ = "notification_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notification_logs_dedup"),
        CheckConstraint(check_in("kind", NotificationKind), name="kind_valid"),
        CheckConstraint(check_in("status", NotificationStatus), name="status_valid"),
        Index("ix_notification_logs_user_time", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(300), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Résumé des éléments inclus (identifiants, titres) — structure variable selon le type.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
