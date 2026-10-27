from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ApplicationStatus, TaskStatus, check_in
from app.models.mixins import Timestamps, UUIDPk


class Application(UUIDPk, Timestamps, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_applications_user_opportunity"),
        UniqueConstraint("id", "user_id", name="uq_applications_id_user"),
        CheckConstraint(check_in("status", ApplicationStatus), name="status_valid"),
        CheckConstraint(
            "status NOT IN ('submitted','selection','accepted') OR submitted_at IS NOT NULL",
            name="submitted_requires_date",
        ),
        CheckConstraint("estimated_prep_hours IS NULL OR estimated_prep_hours BETWEEN 0 AND 500", name="prep_range"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_deadline", "deadline_at"),
        Index("ix_applications_next_action", "next_action_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="to_explore")
    # Échéance personnelle (copie modifiable de celle de l'annonce).
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Preuve de la validation humaine explicite avant tout passage à « envoyée ».
    submission_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    contact_email: Mapped[str | None] = mapped_column(String(320))
    next_action: Mapped[str | None] = mapped_column(String(300))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_notes: Mapped[str | None] = mapped_column(Text)
    response_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_prep_hours: Mapped[int | None] = mapped_column(Integer)


class ApplicationDocument(Base):
    """Association document ↔ candidature. Les clés étrangères composites (id, user_id)
    garantissent en base qu'un document n'est lié qu'à une candidature du même propriétaire."""

    __tablename__ = "application_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "user_id"],
            ["applications.id", "applications.user_id"],
            ondelete="CASCADE",
            name="fk_application_documents_application_owner",
        ),
        ForeignKeyConstraint(
            ["document_id", "user_id"],
            ["documents.id", "documents.user_id"],
            ondelete="CASCADE",
            name="fk_application_documents_document_owner",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ApplicationEvent(UUIDPk, Base):
    """Historique immuable des modifications d'une candidature."""

    __tablename__ = "application_events"
    __table_args__ = (Index("ix_application_events_app_time", "application_id", "created_at"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    # Détail variable selon le type d'événement (champs modifiés, document lié…).
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Task(UUIDPk, Timestamps, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(check_in("status", TaskStatus), name="status_valid"),
        Index("ix_tasks_user_status_due", "user_id", "status", "due_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="todo")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
