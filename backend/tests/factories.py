"""Données de TEST uniquement (jamais insérées en production)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Opportunity, Profile, Source, User
from app.workers.connectors.base import NormalizedOpportunity
from app.workers.ingestion import upsert_opportunity


def make_source(db: Session, key: str = "test-source", connector: str = "greenhouse", **kw: Any) -> Source:
    src = Source(
        key=key,
        name=kw.pop("name", f"Source {key}"),
        connector=connector,
        base_url="https://boards-api.greenhouse.io/v1/boards",
        enabled=kw.pop("enabled", True),
        config=kw.pop("config", {"boards": [{"token": "exemple", "organization": "Exemple SA"}]}),
        rate_limit_seconds=0,
        **kw,
    )
    db.add(src)
    db.commit()
    return src


def make_opportunity(db: Session, source: Source | None = None, **kw: Any) -> Opportunity:
    source = source or make_source(db, key=f"src-{uuid.uuid4().hex[:6]}")
    data: dict[str, Any] = {
        "type": "masters_scholarship",
        "title": "Master conjoint en science des données",
        "organization": "Consortium Test",
        "official_url": f"https://example.org/programme/{uuid.uuid4().hex[:8]}",
        "source_url": "https://example.org/catalogue",
        "description": "Programme de deux ans en data science et machine learning avec Python.",
        "countries": ["DE", "FR"],
        "funding_type": "full",
        "is_official": True,
    }
    data.update(kw)
    if "official_url" in kw and "source_url" not in kw:
        data["source_url"] = kw["official_url"]
    item = NormalizedOpportunity.model_validate(data)
    result = upsert_opportunity(db, source, item)
    db.commit()
    opp = db.get(Opportunity, result.opportunity_id)
    assert opp is not None
    return opp


def make_profile(db: Session, user: User, **kw: Any) -> Profile:
    profile = db.query(Profile).filter_by(user_id=user.id).one_or_none() or Profile(user_id=user.id)
    defaults: dict[str, Any] = {
        "full_name": "Awa Diop",
        "nationalities": ["SN"],
        "study_level": "bachelor",
        "field_of_study": "Informatique",
        "skills": ["Python", "SQL"],
        "languages": [{"code": "fr", "level": "native"}, {"code": "en", "level": "B2"}],
        "target_countries": ["DE"],
        "funding_preference": "full_only",
        "program_types": ["masters_scholarship", "internship"],
    }
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(profile, k, v)
    profile.version = (profile.version or 1) + 1
    db.add(profile)
    db.commit()
    return profile


def in_days(days: float) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)
