from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SourceRef(BaseModel):
    source_key: str
    source_name: str
    source_url: str
    first_seen_at: datetime
    last_seen_at: datetime


class MatchSummary(BaseModel):
    eligibility: str
    score: float
    confidence: float
    computed_at: datetime


class OpportunityListItem(ORMModel):
    id: uuid.UUID
    type: str
    title: str
    organization: str
    countries: list[str]
    location: str | None
    remote: bool | None
    fields: list[str]
    study_levels: list[str]
    funding_type: str
    deadline_at: datetime | None
    deadline_status: str
    status: str
    official_url: str
    verification_status: str
    first_seen_at: datetime
    last_verified_at: datetime | None
    is_favorite: bool = False
    application_id: uuid.UUID | None = None
    application_status: str | None = None
    match: MatchSummary | None = None
    # Offre ajoutée par l'utilisateur à partir d'un lien : visible de lui seul, modifiable et supprimable.
    is_private: bool = False


class OpportunityDetail(OpportunityListItem):
    description: str | None
    eligibility_criteria: str | None
    eligible_nationalities: list[str] | None
    required_languages: list[dict[str, Any]]
    required_documents: list[str]
    funding_amount: str | None
    tuition_covered: bool | None
    stipend: str | None
    benefits: str | None
    duration_months: int | None
    opens_at: date | None
    deadline_timezone: str | None
    tags: list[str]
    last_seen_at: datetime
    content_changed_at: datetime | None
    significant_change_at: datetime | None
    significant_change_fields: list[str]
    sources: list[SourceRef] = []
    match_detail: dict[str, Any] | None = None


SortKey = Literal["deadline", "-deadline", "score", "-score", "recent", "title"]


class OpportunityFilters(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    type: str | None = None
    country: str | None = Field(default=None, max_length=2)
    field: str | None = Field(default=None, max_length=120)
    organization: str | None = Field(default=None, max_length=200)
    study_level: str | None = None
    funding: Literal["full", "partial", "full_or_partial"] | None = None
    deadline_within_days: int | None = Field(default=None, ge=1, le=730)
    include_closed: bool = False
    eligibility: Literal["eligible", "ineligible", "unknown"] | None = None
    min_score: int | None = Field(default=None, ge=0, le=100)
    application_status: str | None = None
    tracked: bool | None = None
    favorites_only: bool = False
    sort: SortKey = "-score"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class FacetsOut(BaseModel):
    countries: list[str]
    fields: list[str]
    organizations: list[str]
    types: list[str]
