"""Offres personnelles ajoutées à partir d'un lien : analyse (rien n'est enregistré), relecture, enregistrement.

Les offres ajoutées sont PRIVÉES : visibles, modifiables et supprimables par leur seul auteur, jamais modifiées
par la collecte. Elles restent « non vérifiées » : relues par l'utilisateur, pas confirmées par la source.

LinkedIn n'est jamais interrogé (connexion requise, robots.txt) : l'identifiant de l'offre, et parfois son
intitulé et l'entreprise, sont lus dans l'adresse du lien ; le reste vient du texte que l'utilisateur colle,
analysé par l'IA si elle est configurée (valeurs vérifiées dans le texte) ou par des règles simples.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, Forbidden, NotFound, ServiceUnavailable, TooManyRequests
from app.core.logging import log_event
from app.core.text import normalize_text, normalize_url
from app.core.timeutil import safe_zone, utcnow
from app.models import Application, AuthAttempt, Opportunity, User
from app.models.enums import DeadlineStatus
from app.schemas.application import ApplicationCreate
from app.schemas.link_import import (
    ImportDraft,
    ImportIn,
    ImportOut,
    ImportPreviewOut,
    OpportunityFields,
    QuickImportIn,
    QuickImportItem,
    QuickImportOut,
)
from app.services import ai, matching
from app.services.applications import create_application
from app.services.visibility import visible_to
from app.workers.connectors.base import NormalizedOpportunity
from app.workers.ingestion import content_hash
from app.workers.link_import import (
    Extraction,
    InvalidLink,
    LinkImportError,
    SafeFetcher,
    check_url_shape,
    extract,
    extract_from_text_rules,
    extraction_from_linkedin,
    parse_linkedin,
)

logger = logging.getLogger("app.link_import")

PREVIEWS_PER_HOUR = 30
# Offres privées : seul leur auteur est concerné, la limite protège surtout contre un script emballé.
IMPORTS_PER_DAY = 200
DRAFT_LIMITS = {"title": 400, "organization": 300, "location": 300, "stipend": 200}
PLACEHOLDER_ORGANIZATION = "À préciser"

# Remplacé dans les tests (transport HTTP simulé, résolution DNS contrôlée).
make_fetcher: Callable[[], SafeFetcher] = SafeFetcher


def _recent(db: Session, key: str, window: timedelta) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(AuthAttempt)
            .where(AuthAttempt.key == key, AuthAttempt.attempted_at >= utcnow() - window)
        )
        or 0
    )


def _limit(db: Session, key: str, window: timedelta, maximum: int, message: str, count: int = 1) -> None:
    if _recent(db, key, window) + count > maximum:
        raise TooManyRequests(message)
    for _ in range(count):
        db.add(AuthAttempt(key=key, success=True))


def _valid_link(url: str) -> str:
    try:
        check_url_shape(url)
    except InvalidLink as exc:
        raise AppError(str(exc), code="invalid_link", status_code=422) from exc
    return url.strip()


def _official_url(url: str) -> str:
    """Adresse de référence : la forme canonique pour LinkedIn (sans paramètres de suivi)."""
    job = parse_linkedin(url)
    return job.canonical_url if job and job.canonical_url else url.strip()


def find_for_user(db: Session, user: User, url: str) -> Opportunity | None:
    """Offre déjà visible pour l'utilisateur à cette adresse (la sienne de préférence, sinon le catalogue commun)."""
    return db.scalar(
        select(Opportunity)
        .where(Opportunity.canonical_url == normalize_url(url), visible_to(user.id))
        .order_by(Opportunity.owner_user_id.is_(None))
        .limit(1)
    )


# ------------------------------------------------------------------ analyse
def _from_text(text: str) -> tuple[dict[str, Any], list[str], bool]:
    provider = ai.get_provider()
    notes: list[str] = []
    if provider is not None:
        try:
            fields = ai.extract_offer(provider, text)
        except ServiceUnavailable as exc:
            notes.append(f"Analyse IA indisponible ({exc.message}) : analyse simple du texte.")
        else:
            rules = extract_from_text_rules(text)
            fields.setdefault("description", rules.fields.get("description"))
            notes.append("Texte analysé par l'IA : seules les informations présentes dans le texte sont reprises.")
            if fields.get("deadline_date"):
                notes.append("Date limite trouvée dans le texte : vérifiez-la avant de la confirmer.")
            return fields, notes, True
    rules = extract_from_text_rules(text)
    notes.extend(rules.notes)
    if provider is None:
        notes.append(
            "Astuce : avec l'assistant IA configuré, l'intitulé, l'entreprise, le lieu et les critères seraient remplis."
        )
    return rules.fields, notes, False


def preview(db: Session, user: User, url: str, text: str | None = None) -> ImportPreviewOut:
    _limit(
        db,
        f"import-preview:{user.id}",
        timedelta(hours=1),
        PREVIEWS_PER_HOUR,
        "Trop d'analyses de liens : réessayez dans une heure.",
    )
    db.commit()
    url = _valid_link(url)
    official = _official_url(url)
    existing = find_for_user(db, user, official)
    if existing is not None:
        return ImportPreviewOut(
            url=url,
            existing_opportunity_id=existing.id,
            fetched=False,
            method="none",
            notes=["Cette offre est déjà enregistrée."],
            draft=ImportDraft(official_url=official),
        )

    linkedin = parse_linkedin(url)
    if linkedin is not None:
        result = extraction_from_linkedin(linkedin)
    else:
        try:
            with make_fetcher() as fetcher:
                result = extract(url, fetcher)
        except InvalidLink as exc:
            raise AppError(str(exc), code="invalid_link", status_code=422) from exc
        except LinkImportError as exc:
            log_event(logger, "link import: not fetched", logging.INFO, reason=exc.__class__.__name__)
            result = Extraction("none", {}, [str(exc)], False)

    fields = {k: v for k, v in result.fields.items() if v not in (None, "", [])}
    notes = list(result.notes)
    ai_used = False
    if text and text.strip():
        text_fields, text_notes, ai_used = _from_text(text)
        # Le texte collé par l'utilisateur prime sur ce que l'adresse ou la page laissaient deviner.
        fields.update({k: v for k, v in text_fields.items() if v not in (None, "", [])})
        notes.extend(text_notes)
    elif not result.fetched:
        notes.append("Complétez les informations ci-dessous, ou collez le texte de l'offre puis relancez l'analyse.")

    for key, limit in DRAFT_LIMITS.items():
        if isinstance(fields.get(key), str):
            fields[key] = fields[key][:limit]
    official = str(fields.pop("official_url", None) or official)
    draft = ImportDraft(official_url=official, **{k: v for k, v in fields.items() if k in ImportDraft.model_fields})
    missing = [
        label
        for key, label in (("type", "le type"), ("title", "l'intitulé"), ("organization", "l'organisme"))
        if not getattr(draft, key)
    ]
    if missing:
        notes.append("À compléter : " + ", ".join(missing) + ".")
    if draft.deadline_date is None:
        notes.append("Aucune date limite trouvée : indiquez-la si elle est publiée.")
    log_event(logger, "link import: preview", method=result.method, ai=ai_used)
    existing = find_for_user(db, user, official)
    return ImportPreviewOut(
        url=url,
        existing_opportunity_id=existing.id if existing else None,
        fetched=result.fetched,
        method=result.method + ("+texte" if text and text.strip() else ""),
        ai_used=ai_used,
        notes=notes,
        draft=draft,
    )


# ------------------------------------------------------------------ enregistrement
def _deadline(data: OpportunityFields, user: User) -> tuple[datetime | None, DeadlineStatus]:
    if data.deadline_date is None:
        return None, DeadlineStatus.UNKNOWN
    local = datetime.combine(data.deadline_date, time(23, 59, 59), tzinfo=safe_zone(user.timezone))
    status = DeadlineStatus.CONFIRMED if data.deadline_confirmed else DeadlineStatus.UNVERIFIED
    return local.astimezone(UTC), status


def _columns(data: OpportunityFields, user: User, official_url: str) -> dict[str, Any]:
    deadline_at, deadline_status = _deadline(data, user)
    try:
        item = NormalizedOpportunity(
            type=data.type,
            title=data.title,
            organization=data.organization,
            official_url=official_url,
            source_url=official_url,
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
        )
    except ValidationError as exc:
        raise AppError("Informations invalides.", code="validation_error", status_code=422) from exc
    values = item.model_dump(exclude={"source_url", "raw", "is_official", "external_id"})
    values["type"] = item.type.value
    values["funding_type"] = item.funding_type.value
    values["deadline_status"] = item.deadline_status.value
    return values


def _apply(opp: Opportunity, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(opp, key, value)
    opp.title_norm = normalize_text(values["title"])
    opp.organization_norm = normalize_text(values["organization"])
    opp.canonical_url = normalize_url(values["official_url"])
    opp.content_hash = content_hash(values)


def _create_private(db: Session, user: User, data: OpportunityFields, official_url: str) -> Opportunity:
    now = utcnow()
    opp = Opportunity(
        owner_user_id=user.id,
        external_id=None,
        primary_source_id=None,
        first_seen_at=now,
        last_seen_at=now,
        verification_status="unverified",
        status="open",
    )
    _apply(opp, _columns(data, user, official_url))
    db.add(opp)
    db.flush()
    return opp


def _follow(db: Session, user: User, opp: Opportunity) -> uuid.UUID:
    try:
        return create_application(db, user, ApplicationCreate(opportunity_id=opp.id)).id
    except Conflict as exc:
        return uuid.UUID(str((exc.details or {}).get("application_id")))


def create(db: Session, user: User, data: ImportIn) -> ImportOut:
    _limit(
        db,
        f"import:{user.id}",
        timedelta(days=1),
        IMPORTS_PER_DAY,
        f"Limite de {IMPORTS_PER_DAY} ajouts par jour atteinte : réessayez demain.",
    )
    official = _official_url(_valid_link(data.official_url))
    opp = find_for_user(db, user, official)
    created = opp is None
    if opp is None:
        opp = _create_private(db, user, data, official)
    db.commit()
    matching.ensure_match(db, user, opp)
    db.commit()
    application_id = _follow(db, user, opp) if data.follow else None
    log_event(logger, "link import: saved", created=created, followed=data.follow)
    message = "Offre enregistrée dans votre liste." if created else "Cette offre était déjà enregistrée."
    return ImportOut(opportunity_id=opp.id, created=created, application_id=application_id, message=message)


def quick_save(db: Session, user: User, data: QuickImportIn) -> QuickImportOut:
    """Plusieurs liens d'un coup, sans lecture des pages : chaque offre est enregistrée et suivie (« À explorer »)."""
    urls = list(dict.fromkeys(u.strip() for u in data.urls if u and u.strip()))
    _limit(
        db,
        f"import:{user.id}",
        timedelta(days=1),
        IMPORTS_PER_DAY,
        f"Limite de {IMPORTS_PER_DAY} ajouts par jour atteinte : réessayez demain.",
        count=len(urls),
    )
    db.commit()
    items: list[QuickImportItem] = []
    for url in urls:
        try:
            check_url_shape(url)
        except InvalidLink as exc:
            items.append(QuickImportItem(url=url, error=str(exc)))
            continue
        if len(url) > 1000:
            items.append(QuickImportItem(url=url[:1000], error="Lien trop long."))
            continue
        job = parse_linkedin(url)
        if job is not None and job.job_id is None:
            items.append(QuickImportItem(url=url, error="Lien LinkedIn sans identifiant d'offre."))
            continue
        official = job.canonical_url if job and job.canonical_url else url
        opp = find_for_user(db, user, official)
        created = opp is None
        if opp is None:
            host = (urlsplit(official).hostname or "").removeprefix("www.")
            title = (job.title if job else None) or (
                f"Offre LinkedIn n° {job.job_id}" if job else f"Offre à compléter — {host}"
            )
            fields = OpportunityFields(
                official_url=official,
                type=data.type,
                title=title[:400] if len(title) >= 3 else f"Offre — {host}",
                organization=(job.organization if job else None) or PLACEHOLDER_ORGANIZATION,
            )
            opp = _create_private(db, user, fields, official)
            db.commit()
            matching.ensure_match(db, user, opp)
            db.commit()
        application_id = _follow(db, user, opp)
        items.append(
            QuickImportItem(
                url=url, opportunity_id=opp.id, application_id=application_id, created=created, title=opp.title
            )
        )
    log_event(logger, "link import: quick save", count=len(urls))
    return QuickImportOut(
        items=items,
        created=sum(1 for i in items if i.created),
        already_saved=sum(1 for i in items if i.opportunity_id and not i.created),
        errors=sum(1 for i in items if i.error),
    )


# ------------------------------------------------------------------ modification / suppression par l'auteur
def _owned(db: Session, user: User, opportunity_id: uuid.UUID) -> Opportunity:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None or (opp.owner_user_id is not None and opp.owner_user_id != user.id):
        raise NotFound("Opportunité introuvable.")
    if opp.owner_user_id is None:
        raise Forbidden("Seules les offres que vous avez ajoutées peuvent être modifiées.", code="not_owner")
    return opp


def update(db: Session, user: User, opportunity_id: uuid.UUID, data: OpportunityFields) -> uuid.UUID:
    opp = _owned(db, user, opportunity_id)
    official = _official_url(_valid_link(data.official_url))
    other = db.scalar(
        select(Opportunity.id).where(
            Opportunity.owner_user_id == user.id,
            Opportunity.canonical_url == normalize_url(official),
            Opportunity.id != opp.id,
        )
    )
    if other is not None:
        raise Conflict("Une autre de vos offres utilise déjà ce lien.", code="duplicate_link")
    before = opp.content_hash
    _apply(opp, _columns(data, user, official))
    if opp.content_hash != before:
        opp.content_changed_at = utcnow()
    db.commit()
    matching.ensure_match(db, user, opp)
    db.commit()
    return opp.id


def remove(db: Session, user: User, opportunity_id: uuid.UUID) -> None:
    opp = _owned(db, user, opportunity_id)
    # Les candidatures référencent l'offre (RESTRICT) : seule celle de l'auteur peut exister sur une offre privée.
    db.execute(delete(Application).where(Application.opportunity_id == opp.id, Application.user_id == user.id))
    db.delete(opp)
    db.commit()
    log_event(logger, "link import: deleted")
