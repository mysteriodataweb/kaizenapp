from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import DigestFrequency, DocumentType
from app.schemas.common import ORMModel


# ---------- Documents ----------
class DocumentOut(ORMModel):
    id: uuid.UUID
    group_id: uuid.UUID
    version: int
    doc_type: str
    title: str
    original_filename: str
    mime_type: str
    size_bytes: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    application_ids: list[uuid.UUID] = []


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    doc_type: DocumentType | None = None
    notes: str | None = Field(default=None, max_length=5000)


class DownloadLink(BaseModel):
    mode: str  # "redirect" (URL signée) ou "proxy" (flux via l'API)
    url: str
    expires_in: int


# ---------- Notifications ----------
class NotificationPrefsIn(BaseModel):
    email: EmailStr | None = None
    enabled: bool = True
    digest_frequency: DigestFrequency = DigestFrequency.WEEKLY
    digest_weekday: int = Field(default=0, ge=0, le=6)
    digest_hour: int = Field(default=8, ge=0, le=23)
    notify_new_matches: bool = True
    notify_deadlines: bool = True
    notify_tasks: bool = True
    notify_changes: bool = True
    notify_ingestion_errors: bool = True
    min_score: int = Field(default=60, ge=0, le=100)
    max_items: int = Field(default=10, ge=1, le=50)
    deadline_reminder_days: list[int] = Field(default_factory=lambda: [14, 7, 3, 1], max_length=8)

    @field_validator("deadline_reminder_days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 90 for d in v):
            raise ValueError("Les rappels doivent être compris entre J-0 et J-90.")
        return sorted(set(v), reverse=True)


class NotificationPrefsOut(ORMModel, NotificationPrefsIn):
    email: str | None = None  # type: ignore[assignment]
    last_digest_sent_at: datetime | None = None
    email_mode: str = "simulation"
    effective_recipient: str | None = None


class NotificationLogOut(ORMModel):
    id: uuid.UUID
    kind: str
    dedup_key: str
    recipient: str
    subject: str
    status: str
    provider: str
    provider_message_id: str | None
    attempts: int
    last_error: str | None
    payload: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None


class NotificationPreview(BaseModel):
    kind: str
    subject: str
    html: str
    text: str
    items: int
    note: str | None = None


class TestEmailIn(BaseModel):
    confirm: bool = Field(description="Doit être vrai : confirmation explicite de l'envoi.")


# ---------- Administration ----------
class SourceOut(ORMModel):
    id: uuid.UUID
    key: str
    name: str
    connector: str
    base_url: str
    description: str | None
    terms_notes: str | None
    enabled: bool
    config: dict[str, Any]
    rate_limit_seconds: float
    max_items: int
    verification_status: str
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_tested_at: datetime | None
    consecutive_failures: int
    last_error: str | None
    opportunities_count: int = 0


class SourceUpdate(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    rate_limit_seconds: float | None = Field(default=None, ge=0.5, le=60)
    max_items: int | None = Field(default=None, ge=1, le=2000)


class IngestionRunOut(ORMModel):
    id: uuid.UUID
    source_id: uuid.UUID | None
    job_name: str
    triggered_by: str
    dry_run: bool
    status: str
    started_at: datetime
    finished_at: datetime | None
    items_fetched: int
    items_created: int
    items_updated: int
    items_unchanged: int
    items_skipped: int
    errors_count: int
    details: dict[str, Any]


class SourceTestOut(BaseModel):
    source_key: str
    ok: bool
    items_found: int
    sample: list[dict[str, Any]]
    errors: list[str]
    verification_status: str
    duration_ms: int


# ---------- Assistant IA ----------
class AssistRequest(BaseModel):
    kind: str = Field(pattern=r"^(cover_letter|cv_tailoring|application_answers|email_draft|interview_prep)$")
    opportunity_id: uuid.UUID
    instructions: str | None = Field(default=None, max_length=2000)
    questions: list[str] = Field(default_factory=list, max_length=10)


class AssistOut(BaseModel):
    enabled: bool
    kind: str
    draft: str | None
    missing_information: list[str]
    used_fields: list[str]
    warning: str
