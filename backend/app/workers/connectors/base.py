"""Contrat commun des connecteurs et validation des annonces normalisées."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import DeadlineStatus, FundingType, OpportunityType
from app.workers.connectors.http import PoliteClient

INTERNSHIP_RE = re.compile(
    r"(?<![\w])(intern|interns|internship|internships|stage|stagiaire|trainee|traineeship|praktikum|praktikant|"
    r"praktikantin|werkstudent|working student|summer analyst|co-op|alternance|apprenti|apprentice)(?![\w])",
    re.I,
)


class NormalizedOpportunity(BaseModel):
    """Annonce validée avant enregistrement. Une URL officielle est obligatoire (provenance)."""

    external_id: str | None = Field(default=None, max_length=200)
    type: OpportunityType
    title: str = Field(min_length=3, max_length=400)
    organization: str = Field(min_length=1, max_length=300)
    official_url: str = Field(max_length=1000)
    source_url: str = Field(max_length=1000)
    description: str | None = Field(default=None, max_length=60000)
    countries: list[str] = Field(default_factory=list)
    location: str | None = Field(default=None, max_length=300)
    remote: bool | None = None
    fields: list[str] = Field(default_factory=list)
    study_levels: list[str] = Field(default_factory=list)
    eligibility_criteria: str | None = Field(default=None, max_length=20000)
    eligible_nationalities: list[str] | None = None
    required_languages: list[dict[str, Any]] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    funding_type: FundingType = FundingType.UNKNOWN
    funding_amount: str | None = Field(default=None, max_length=200)
    tuition_covered: bool | None = None
    stipend: str | None = Field(default=None, max_length=200)
    benefits: str | None = Field(default=None, max_length=5000)
    duration_months: int | None = Field(default=None, ge=0, le=60)
    opens_at: date | None = None
    deadline_at: datetime | None = None
    deadline_timezone: str | None = None
    deadline_status: DeadlineStatus = DeadlineStatus.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    is_official: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("official_url", "source_url")
    @classmethod
    def _http_url(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", v, re.I):
            raise ValueError("URL http(s) valide requise.")
        return v

    @field_validator("title", "organization")
    @classmethod
    def _clean(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("countries")
    @classmethod
    def _countries(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(c.upper() for c in v if re.fullmatch(r"[A-Za-z]{2}", c)))

    @field_validator("fields", "tags", "required_documents")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        out: dict[str, str] = {}
        for item in v:
            item = " ".join(str(item).split())[:100]
            if item and item.lower() not in out:
                out[item.lower()] = item
        return list(out.values())[:40]

    @model_validator(mode="after")
    def _deadline(self) -> NormalizedOpportunity:
        if self.deadline_at is None:
            self.deadline_status = DeadlineStatus.UNKNOWN
        elif self.deadline_status == DeadlineStatus.UNKNOWN:
            self.deadline_status = DeadlineStatus.UNVERIFIED
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            self.deadline_at = self.deadline_at.replace(tzinfo=UTC)
        return self


class ParseIssue(BaseModel):
    item: str
    error: str


class Connector(ABC):
    """Un connecteur interroge UNE source publique et autorisée et produit des annonces normalisées."""

    name: ClassVar[str]
    # Vrai si la source publie elle-même les annonces (site/API officiels de l'organisme).
    official: ClassVar[bool] = True
    # Vrai si un passage complet sans erreur liste TOUTES les annonces actives (permet de clore les absentes).
    complete_listing: ClassVar[bool] = False

    def __init__(self, config: dict[str, Any], http: PoliteClient, max_items: int = 200):
        self.config = config or {}
        self.http = http
        self.max_items = max_items
        self.issues: list[ParseIssue] = []
        self.truncated = False

    @abstractmethod
    def fetch(self) -> Iterator[dict[str, Any]]:
        """Produit des dictionnaires prêts pour NormalizedOpportunity (validation faite par le pipeline)."""

    def issue(self, item: str, error: str) -> None:
        self.issues.append(ParseIssue(item=item[:200], error=error[:500]))


def is_internship_title(title: str, extra: list[str] | None = None) -> bool:
    if INTERNSHIP_RE.search(title):
        return True
    return any(k.lower() in title.lower() for k in (extra or []))


_MONTHS = {
    "january": 1,
    "janvier": 1,
    "januar": 1,
    "jan": 1,
    "february": 2,
    "fevrier": 2,
    "février": 2,
    "februar": 2,
    "feb": 2,
    "march": 3,
    "mars": 3,
    "märz": 3,
    "marz": 3,
    "mar": 3,
    "april": 4,
    "avril": 4,
    "apr": 4,
    "may": 5,
    "mai": 5,
    "june": 6,
    "juin": 6,
    "juni": 6,
    "jun": 6,
    "july": 7,
    "juillet": 7,
    "juli": 7,
    "jul": 7,
    "august": 8,
    "aout": 8,
    "août": 8,
    "aug": 8,
    "september": 9,
    "septembre": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "octobre": 10,
    "oktober": 10,
    "oct": 10,
    "okt": 10,
    "november": 11,
    "novembre": 11,
    "nov": 11,
    "december": 12,
    "decembre": 12,
    "décembre": 12,
    "dezember": 12,
    "dec": 12,
    "dez": 12,
}
_DEADLINE_KW = re.compile(
    r"(deadline|date limite|apply by|applications? close|closing date|bewerbungsschluss|until|jusqu'au|avant le)",
    re.I,
)
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_PATTERNS = [
    re.compile(r"(?P<y>20\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})"),
    re.compile(r"(?P<d>\d{1,2})[./](?P<m>\d{1,2})[./](?P<y>20\d{2})"),
    re.compile(rf"(?P<d>\d{{1,2}})(?:er|st|nd|rd|th)?\.?\s+(?P<mon>{_MONTH_NAMES})\.?,?\s+(?P<y>20\d{{2}})", re.I),
    re.compile(rf"(?P<mon>{_MONTH_NAMES})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>20\d{{2}})", re.I),
]


def extract_deadline(text: str | None) -> datetime | None:
    """Cherche une date proche d'un mot-clé d'échéance. Retourne la fin de journée UTC.
    Le résultat doit être marqué « non vérifié » par l'appelant."""
    if not text:
        return None
    for kw in _DEADLINE_KW.finditer(text):
        window = text[kw.end() : kw.end() + 80]
        for pattern in _DATE_PATTERNS:
            m = pattern.search(window)
            if not m:
                continue
            try:
                month = int(m.group("m")) if "m" in m.groupdict() and m.group("m") else _MONTHS[m.group("mon").lower()]
                d = date(int(m.group("y")), month, int(m.group("d")))
            except (ValueError, KeyError):
                continue
            return datetime.combine(d, time(23, 59, 59), tzinfo=UTC)
    return None


def parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            ts = value / 1000 if value > 10_000_000_000 else value
            return datetime.fromtimestamp(ts, tz=UTC)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except (ValueError, OverflowError, OSError):
        return None
