from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import ApplicationStatus, TaskStatus
from app.schemas.common import ORMModel


class ApplicationCreate(BaseModel):
    opportunity_id: uuid.UUID
    status: ApplicationStatus = ApplicationStatus.TO_EXPLORE
    notes: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def _initial_status(self) -> ApplicationCreate:
        if self.status not in (
            ApplicationStatus.TO_EXPLORE,
            ApplicationStatus.TO_PREPARE,
            ApplicationStatus.PREPARING,
        ):
            raise ValueError("Une nouvelle candidature commence en exploration ou en préparation.")
        return self


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    # Obligatoire et vrai pour passer à « envoyée » : validation humaine explicite.
    confirm_submission: bool = False
    deadline_at: datetime | None = None
    submitted_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=20000)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    next_action: str | None = Field(default=None, max_length=300)
    next_action_at: datetime | None = None
    follow_up_at: datetime | None = None
    response_notes: str | None = Field(default=None, max_length=20000)
    response_received_at: datetime | None = None
    estimated_prep_hours: int | None = Field(default=None, ge=0, le=500)


class OpportunityBrief(ORMModel):
    id: uuid.UUID
    type: str
    title: str
    organization: str
    official_url: str
    deadline_at: datetime | None
    deadline_status: str
    status: str
    required_documents: list[str]
    countries: list[str]


class UrgencyOut(BaseModel):
    level: str
    score: int
    reasons: list[str]
    days_left: int | None


class LinkedDocument(BaseModel):
    id: uuid.UUID
    title: str
    doc_type: str
    version: int
    role: str | None
    added_at: datetime


class ApplicationOut(ORMModel):
    id: uuid.UUID
    opportunity: OpportunityBrief
    status: str
    deadline_at: datetime | None
    submitted_at: datetime | None
    submission_confirmed_at: datetime | None
    notes: str | None
    contact_name: str | None
    contact_email: str | None
    next_action: str | None
    next_action_at: datetime | None
    follow_up_at: datetime | None
    response_notes: str | None
    response_received_at: datetime | None
    estimated_prep_hours: int | None
    created_at: datetime
    updated_at: datetime
    urgency: UrgencyOut | None = None
    eligibility: str | None = None
    score: float | None = None
    documents: list[LinkedDocument] = []
    open_tasks: int = 0


class ApplicationEventOut(ORMModel):
    id: uuid.UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    details: dict[str, Any]
    created_at: datetime


class LinkDocumentIn(BaseModel):
    document_id: uuid.UUID
    role: str | None = Field(default=None, max_length=120)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    application_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    status: TaskStatus | None = None


class TaskOut(ORMModel):
    id: uuid.UUID
    application_id: uuid.UUID | None
    title: str
    description: str | None
    due_at: datetime | None
    status: str
    completed_at: datetime | None
    created_at: datetime
    overdue: bool = False
    application_title: str | None = None
