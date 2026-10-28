"""Ajout d'une offre à partir d'un lien : analyse (rien n'est enregistré), relecture par l'utilisateur,
puis enregistrement par le pipeline commun (validation, dédoublonnage, provenance, matching).

Les offres ajoutées rejoignent le catalogue commun avec la provenance « Ajouts manuels » et restent
« non vérifiées » : le contenu relu par l'utilisateur ne vaut pas confirmation par la source officielle.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, TooManyRequests
from app.core.logging import log_event
from app.core.text import normalize_url
from app.core.timeutil import safe_zone, utcnow
from app.models import AuthAttempt, Opportunity, Source, User
from app.models.enums import DeadlineStatus
from app.schemas.application import ApplicationCreate
from app.schemas.link_import import ImportDraft, ImportIn, ImportOut, ImportPreviewOut
from app.services import matching
from app.services.applications import create_application
from app.workers.connectors.base import NormalizedOpportunity
from app.workers.ingestion import upsert_opportunity
from app.workers.link_import import InvalidLink, LinkImportError, SafeFetcher, check_url_shape, extract

logger = logging.getLogger("app.link_import")

MANUAL_SOURCE_KEY = "manual-links"
MANUAL_CONNECTOR = "manual"
PREVIEWS_PER_HOUR = 30
IMPORTS_PER_DAY = 20
DRAFT_LIMITS = {"title": 400, "organization": 300, "location": 300, "stipend": 200}

# Remplacé dans les tests (transport HTTP simulé, résolution DNS contrôlée).
make_fetcher: Callable[[], SafeFetcher] = SafeFetcher


def _limit(db: Session, key: str, window: timedelta, maximum: int, message: str) -> None:
    count = db.scalar(
        select(func.count())
        .select_from(AuthAttempt)
        .where(AuthAttempt.key == key, AuthAttempt.attempted_at >= utcnow() - window)
    )
    if (count or 0) >= maximum:
        raise TooManyRequests(message)
    db.add(AuthAttempt(key=key, success=True))


def manual_source(db: Session) -> Source:
    db.execute(
        insert(Source)
        .values(
            key=MANUAL_SOURCE_KEY,
            name="Ajouts manuels (liens partagés par les utilisateurs)",
            connector=MANUAL_CONNECTOR,
            base_url="https://",
            description="Offres ajoutées à partir d'un lien, relues par l'utilisateur avant enregistrement.",
            terms_notes="Une page lue à la demande de l'utilisateur, robots.txt respecté, sans contournement.",
            enabled=False,
        )
        .on_conflict_do_nothing(index_elements=["key"])
    )
    source = db.scalar(select(Source).where(Source.key == MANUAL_SOURCE_KEY))
    assert source is not None
    return source


def _existing(db: Session, url: str) -> uuid.UUID | None:
    return db.scalar(select(Opportunity.id).where(Opportunity.canonical_url == normalize_url(url)))


def preview(db: Session, user: User, url: str) -> ImportPreviewOut:
    _limit(
        db,
        f"import-preview:{user.id}",
        timedelta(hours=1),
        PREVIEWS_PER_HOUR,
        "Trop d'analyses de liens : réessayez dans une heure.",
    )
    db.commit()
    url = url.strip()
    try:
        check_url_shape(url)
    except InvalidLink as exc:
        raise AppError(str(exc), code="invalid_link", status_code=422) from exc
    existing = _existing(db, url)
    if existing:
        return ImportPreviewOut(
            url=url,
            existing_opportunity_id=existing,
            fetched=False,
            method="none",
            notes=["Cette offre est déjà dans le catalogue."],
            draft=ImportDraft(official_url=url),
        )
    try:
        with make_fetcher() as fetcher:
            result = extract(url, fetcher)
    except InvalidLink as exc:
        raise AppError(str(exc), code="invalid_link", status_code=422) from exc
    except LinkImportError as exc:
        log_event(logger, "link import: not fetched", logging.INFO, reason=exc.__class__.__name__)
        return ImportPreviewOut(
            url=url,
            fetched=False,
            method="none",
            notes=[str(exc), "Complétez les informations ci-dessous à partir de la page de l'offre."],
            draft=ImportDraft(official_url=url),
        )

    fields = {k: v for k, v in result.fields.items() if k in ImportDraft.model_fields and v not in (None, "", [])}
    for key, limit in DRAFT_LIMITS.items():
        if isinstance(fields.get(key), str):
            fields[key] = fields[key][:limit]
    official = str(fields.pop("official_url", None) or url)
    draft = ImportDraft(official_url=official, **fields)
    notes = list(result.notes)
    missing = [
        label
        for key, label in (("type", "le type"), ("title", "le titre"), ("organization", "l'organisme"))
        if not getattr(draft, key)
    ]
    if missing:
        notes.append("À compléter : " + ", ".join(missing) + ".")
    if draft.deadline_date is None:
        notes.append("Aucune date limite trouvée : indiquez-la si elle est publiée.")
    log_event(logger, "link import: preview", method=result.method)
    return ImportPreviewOut(
        url=url,
        existing_opportunity_id=_existing(db, official),
        fetched=True,
        method=result.method,
        notes=notes,
        draft=draft,
    )


def _deadline(data: ImportIn, user: User) -> tuple[datetime | None, DeadlineStatus]:
    if data.deadline_date is None:
        return None, DeadlineStatus.UNKNOWN
    local = datetime.combine(data.deadline_date, time(23, 59, 59), tzinfo=safe_zone(user.timezone))
    status = DeadlineStatus.CONFIRMED if data.deadline_confirmed else DeadlineStatus.UNVERIFIED
    return local.astimezone(UTC), status


def create(db: Session, user: User, data: ImportIn) -> ImportOut:
    _limit(
        db,
        f"import:{user.id}",
        timedelta(days=1),
        IMPORTS_PER_DAY,
        f"Limite de {IMPORTS_PER_DAY} ajouts par jour atteinte : réessayez demain.",
    )
    try:
        check_url_shape(data.official_url)
    except InvalidLink as exc:
        raise AppError(str(exc), code="invalid_link", status_code=422) from exc

    opp = db.scalar(select(Opportunity).where(Opportunity.canonical_url == normalize_url(data.official_url)))
    created = False
    if opp is None:
        deadline_at, deadline_status = _deadline(data, user)
        try:
            item = NormalizedOpportunity(
                type=data.type,
                title=data.title,
                organization=data.organization,
                official_url=data.official_url,
                source_url=data.official_url,
                description=data.description,
                countries=data.countries,
                location=data.location,
                remote=data.remote,
                fields=data.fields,
                study_levels=[level.value for level in data.study_levels],
                eligibility_criteria=data.eligibility_criteria,
                funding_type=data.funding_type,
                funding_amount=data.funding_amount,
                stipend=data.stipend,
                duration_months=data.duration_months,
                required_documents=data.required_documents,
                deadline_at=deadline_at,
                deadline_timezone=user.timezone if deadline_at else None,
                deadline_status=deadline_status,
                is_official=False,
                raw={"submitted_by": str(user.id), "manual": True},
            )
        except ValidationError as exc:
            raise AppError("Informations invalides.", code="validation_error", status_code=422) from exc
        # Un ajout manuel ne modifie jamais une offre existante : le pipeline crée l'offre ou la rattache
        # à une annonce identique déjà collectée (même titre, organisme, date et lieu).
        result = upsert_opportunity(db, manual_source(db), item)
        opp = db.get(Opportunity, result.opportunity_id)
        assert opp is not None
        created = result.action == "created"
    db.commit()
    matching.ensure_match(db, user, opp)
    db.commit()

    application_id: uuid.UUID | None = None
    if data.follow:
        try:
            application_id = create_application(db, user, ApplicationCreate(opportunity_id=opp.id)).id
        except Conflict as exc:
            application_id = uuid.UUID(str((exc.details or {}).get("application_id")))
    log_event(logger, "link import: saved", created=created, followed=data.follow)
    message = "Offre ajoutée au catalogue." if created else "Cette offre était déjà dans le catalogue."
    return ImportOut(opportunity_id=opp.id, created=created, application_id=application_id, message=message)
