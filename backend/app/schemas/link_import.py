from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.models.enums import FundingType, OpportunityType, StudyLevel
from app.schemas.common import CountryCode, TagList

URL_PATTERN = r"^https?://\S+$"


class ImportPreviewIn(BaseModel):
    url: str = Field(min_length=10, max_length=1000, pattern=URL_PATTERN)
    # Texte de l'offre copié par l'utilisateur (indispensable pour LinkedIn, illisible automatiquement).
    text: str | None = Field(default=None, max_length=30000)


class ImportDraft(BaseModel):
    """Brouillon pré-rempli : chaque champ reste modifiable par l'utilisateur."""

    official_url: str
    type: OpportunityType | None = None
    title: str | None = None
    organization: str | None = None
    description: str | None = None
    location: str | None = None
    countries: list[str] = Field(default_factory=list)
    remote: bool | None = None
    deadline_date: date | None = None
    duration_months: int | None = None
    fields: list[str] = Field(default_factory=list)
    stipend: str | None = None
    required_documents: list[str] = Field(default_factory=list)
    eligibility_criteria: str | None = None


class ImportPreviewOut(BaseModel):
    url: str
    existing_opportunity_id: uuid.UUID | None = None
    fetched: bool
    method: str
    ai_used: bool = False
    notes: list[str]
    draft: ImportDraft


class OpportunityFields(BaseModel):
    """Champs d'une offre ajoutée ou modifiée par son auteur."""

    official_url: str = Field(min_length=10, max_length=1000, pattern=URL_PATTERN)
    type: OpportunityType
    title: str = Field(min_length=3, max_length=400)
    organization: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=30000)
    location: str | None = Field(default=None, max_length=300)
    countries: list[CountryCode] = Field(default_factory=list, max_length=30)
    remote: bool | None = None
    deadline_date: date | None = None
    # Coché par l'utilisateur après vérification sur la page officielle ; sinon la date reste « non vérifiée ».
    deadline_confirmed: bool = False
    study_levels: list[StudyLevel] = Field(default_factory=list, max_length=5)
    fields: TagList = Field(default_factory=list)
    eligibility_criteria: str | None = Field(default=None, max_length=10000)
    funding_type: FundingType = FundingType.UNKNOWN
    funding_amount: str | None = Field(default=None, max_length=200)
    stipend: str | None = Field(default=None, max_length=200)
    duration_months: int | None = Field(default=None, ge=0, le=60)
    required_documents: TagList = Field(default_factory=list)


class ImportIn(OpportunityFields):
    follow: bool = True


class ImportOut(BaseModel):
    opportunity_id: uuid.UUID
    created: bool
    application_id: uuid.UUID | None = None
    message: str


class QuickImportIn(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)
    type: OpportunityType = OpportunityType.INTERNSHIP


class QuickImportItem(BaseModel):
    url: str
    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    created: bool = False
    title: str | None = None
    error: str | None = None


class QuickImportOut(BaseModel):
    items: list[QuickImportItem]
    created: int
    already_saved: int
    errors: int
