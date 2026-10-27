from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import CEFR_LEVELS, FundingPreference, OpportunityType, StudyLevel
from app.schemas.common import CountryCode, LanguageCode, ORMModel, TagList

_YM = r"^\d{4}(-(0[1-9]|1[0-2]))?$"


class LanguageItem(BaseModel):
    code: LanguageCode
    level: str = Field(description="A1…C2 ou native")

    @field_validator("level")
    @classmethod
    def _level(cls, v: str) -> str:
        v = v.strip()
        normalized = "native" if v.lower() in {"native", "natif", "maternelle", "langue maternelle"} else v.upper()
        if normalized not in CEFR_LEVELS:
            raise ValueError("Niveau CECRL attendu : A1, A2, B1, B2, C1, C2 ou native.")
        return normalized


class ExperienceItem(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, pattern=_YM)
    end: str | None = Field(default=None, pattern=_YM)
    current: bool = False
    description: str | None = Field(default=None, max_length=4000)
    skills: TagList = []


class ProjectItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    url: str | None = Field(default=None, max_length=500)
    skills: TagList = []


class LeadershipItem(BaseModel):
    role: str = Field(min_length=1, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, pattern=_YM)
    end: str | None = Field(default=None, pattern=_YM)
    description: str | None = Field(default=None, max_length=4000)


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=120)
    country_of_residence: CountryCode | None = None
    nationalities: list[CountryCode] = Field(default_factory=list, max_length=5)
    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=5000)

    study_level: StudyLevel | None = None
    current_degree: str | None = Field(default=None, max_length=200)
    institution: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    academic_year: str | None = Field(default=None, max_length=50)
    expected_graduation: date | None = None
    academic_results: str | None = Field(default=None, max_length=300)

    skills: TagList = []
    experiences: list[ExperienceItem] = Field(default_factory=list, max_length=50)
    projects: list[ProjectItem] = Field(default_factory=list, max_length=50)
    leadership: list[LeadershipItem] = Field(default_factory=list, max_length=50)
    languages: list[LanguageItem] = Field(default_factory=list, max_length=20)

    target_countries: list[CountryCode] = Field(default_factory=list, max_length=60)
    internship_fields: TagList = []
    master_fields: TagList = []
    funding_preference: FundingPreference | None = None
    program_types: list[OpportunityType] = Field(default_factory=list)
    internship_duration_min_months: int | None = Field(default=None, ge=0, le=36)
    internship_duration_max_months: int | None = Field(default=None, ge=0, le=36)
    accepts_remote: bool | None = None

    @model_validator(mode="after")
    def _consistency(self) -> ProfileIn:
        lo, hi = self.internship_duration_min_months, self.internship_duration_max_months
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("La durée minimale de stage dépasse la durée maximale.")
        codes = [lang.code for lang in self.languages]
        if len(codes) != len(set(codes)):
            raise ValueError("Chaque langue ne peut apparaître qu'une fois.")
        self.nationalities = list(dict.fromkeys(self.nationalities))
        self.target_countries = list(dict.fromkeys(self.target_countries))
        self.program_types = list(dict.fromkeys(self.program_types))
        return self


class ProfileOut(ORMModel, ProfileIn):
    contact_email: str | None = None  # type: ignore[assignment]
    version: int
    updated_at: datetime
    completeness: int = 0
    missing_fields: list[str] = []


class CvExtractionOut(BaseModel):
    """Suggestions extraites d'un CV : jamais enregistrées sans confirmation explicite."""

    text_length: int
    pages: int
    suggestions: dict[str, object]
    evidence: dict[str, str]
    warnings: list[str]
