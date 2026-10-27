"""Registre des connecteurs et sources par défaut (désactivées jusqu'au test réussi)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Source
from app.workers.connectors.base import Connector
from app.workers.connectors.http import PoliteClient
from app.workers.connectors.job_boards import ArbeitnowConnector, GreenhouseConnector, LeverConnector
from app.workers.connectors.scholarships import ErasmusMundusConnector, RssConnector

CONNECTORS: dict[str, type[Connector]] = {
    c.name: c for c in (GreenhouseConnector, LeverConnector, ArbeitnowConnector, ErasmusMundusConnector, RssConnector)
}

DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "key": "erasmus-mundus-catalogue",
        "name": "Erasmus Mundus — catalogue officiel (EACEA)",
        "connector": "erasmus_mundus",
        "base_url": "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en",
        "description": "Masters conjoints Erasmus Mundus proposant des bourses financées par l'UE.",
        "terms_notes": "Page publique de la Commission européenne ; robots.txt respecté ; 1 requête / 3 s.",
        "rate_limit_seconds": 3,
        "max_items": 300,
        "config": {"max_pages": 15},
    },
    {
        "key": "greenhouse-internships",
        "name": "Stages — Greenhouse (boards d'entreprises)",
        "connector": "greenhouse",
        "base_url": "https://boards-api.greenhouse.io/v1/boards",
        "description": "API publique Greenhouse Job Board : offres publiées par les entreprises elles-mêmes.",
        "terms_notes": "API publique documentée (developers.greenhouse.io). Boards à adapter à vos cibles.",
        "rate_limit_seconds": 1,
        "max_items": 300,
        "config": {
            "boards": [
                {"token": "cloudflare", "organization": "Cloudflare"},
                {"token": "datadog", "organization": "Datadog"},
                {"token": "mongodb", "organization": "MongoDB"},
            ]
        },
    },
    {
        "key": "lever-internships",
        "name": "Stages — Lever (pages carrières d'entreprises)",
        "connector": "lever",
        "base_url": "https://api.lever.co/v0/postings",
        "description": "API publique Lever Postings : offres publiées par les entreprises elles-mêmes.",
        "terms_notes": "API publique documentée (github.com/lever/postings-api). Sites à adapter à vos cibles.",
        "rate_limit_seconds": 1,
        "max_items": 300,
        "config": {
            "sites": [
                {"site": "spotify", "organization": "Spotify"},
                {"site": "palantir", "organization": "Palantir"},
                {"site": "mistral", "organization": "Mistral AI"},
            ]
        },
    },
    {
        "key": "arbeitnow-internships",
        "name": "Stages en Allemagne — Arbeitnow (agrégateur)",
        "connector": "arbeitnow",
        "base_url": "https://www.arbeitnow.com/api/job-board-api",
        "description": "API publique gratuite d'Arbeitnow, filtrée sur les stages. Agrégateur : annonces non vérifiées.",
        "terms_notes": "API publique (arbeitnow.com/api) ; 5 pages max par collecte.",
        "rate_limit_seconds": 2,
        "max_items": 200,
        "config": {"max_pages": 5},
    },
    {
        "key": "rss-feeds",
        "name": "Flux RSS officiels (à configurer)",
        "connector": "rss",
        "base_url": "https://",
        "description": "Flux RSS/Atom publics d'universités ou d'organismes (ex. pages « bourses » officielles).",
        "terms_notes": "N'ajoutez que des flux publics dont la réutilisation est autorisée.",
        "rate_limit_seconds": 2,
        "max_items": 200,
        "config": {"feeds": []},
    },
]


def build_connector(source: Source, http: PoliteClient) -> Connector:
    cls = CONNECTORS.get(source.connector)
    if cls is None:
        raise ValueError(f"Connecteur inconnu : {source.connector}")
    return cls(source.config, http, max_items=source.max_items)


def seed_sources(db: Session) -> int:
    """Crée les sources manquantes sans jamais écraser une configuration existante."""
    existing = set(db.scalars(select(Source.key)))
    created = 0
    for spec in DEFAULT_SOURCES:
        if spec["key"] in existing:
            continue
        db.add(Source(enabled=False, verification_status="unverified", **spec))
        created += 1
    db.commit()
    return created
