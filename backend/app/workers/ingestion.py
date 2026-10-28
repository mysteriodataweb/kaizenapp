"""Pipeline de collecte : connecteur -> validation -> dédoublonnage -> enregistrement idempotent.

Dédoublonnage à plusieurs niveaux :
  1. identifiant externe de la source (source, external_id) ;
  2. URL officielle normalisée ;
  3. titre + organisme + date limite + localisation normalisés identiques, et UNIQUEMENT
     depuis une autre source (jamais sur une simple similarité de titre) ;
  4. empreinte de contenu pour détecter les modifications.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.core.text import normalize_text, normalize_url, stable_hash
from app.core.timeutil import utcnow
from app.models import IngestionRun, Opportunity, OpportunitySource, Source
from app.workers.connectors.base import NormalizedOpportunity
from app.workers.connectors.http import AccessDenied, ConnectorError, PoliteClient
from app.workers.connectors.registry import build_connector

logger = logging.getLogger("app.collector")

CONTENT_FIELDS = (
    "type",
    "title",
    "organization",
    "description",
    "countries",
    "location",
    "remote",
    "fields",
    "study_levels",
    "eligibility_criteria",
    "eligible_nationalities",
    "required_languages",
    "required_documents",
    "funding_type",
    "funding_amount",
    "tuition_covered",
    "stipend",
    "benefits",
    "duration_months",
    "opens_at",
    "deadline_at",
    "deadline_timezone",
    "deadline_status",
    "official_url",
    "tags",
)
SIGNIFICANT_FIELDS = (
    "deadline_at",
    "deadline_status",
    "funding_type",
    "funding_amount",
    "eligible_nationalities",
    "study_levels",
    "required_languages",
    "required_documents",
    "title",
    "official_url",
)


def content_hash(data: dict[str, Any]) -> str:
    return stable_hash({k: data.get(k) for k in CONTENT_FIELDS})


def _deadline_key(dt: datetime | None) -> date | None:
    return dt.date() if dt else None


@dataclass
class UpsertResult:
    action: str  # created | updated | unchanged | linked
    opportunity_id: Any
    significant_changes: list[str] = field(default_factory=list)


def upsert_opportunity(db: Session, source: Source, item: NormalizedOpportunity) -> UpsertResult:
    now = utcnow()
    data = item.model_dump(exclude={"source_url", "raw", "is_official", "external_id"})
    data["type"] = item.type.value
    data["funding_type"] = item.funding_type.value
    data["deadline_status"] = item.deadline_status.value
    canonical = normalize_url(item.official_url)
    title_norm, org_norm = normalize_text(item.title), normalize_text(item.organization)
    new_hash = content_hash(data)

    opp: Opportunity | None = None
    if item.external_id:
        opp = db.scalar(
            select(Opportunity).where(
                Opportunity.primary_source_id == source.id,
                Opportunity.external_id == item.external_id,
                Opportunity.owner_user_id.is_(None),
            )
        )
    if opp is None:
        # Les offres privées des utilisateurs ne sont jamais rattachées ni modifiées par la collecte.
        opp = db.scalar(
            select(Opportunity).where(Opportunity.canonical_url == canonical, Opportunity.owner_user_id.is_(None))
        )
    alt_source = False
    if opp is None:
        candidates = db.scalars(
            select(Opportunity).where(
                Opportunity.title_norm == title_norm,
                Opportunity.organization_norm == org_norm,
                Opportunity.type == data["type"],
                Opportunity.primary_source_id != source.id,
                Opportunity.owner_user_id.is_(None),
            )
        ).all()
        for cand in candidates:
            same_deadline = _deadline_key(cand.deadline_at) == _deadline_key(item.deadline_at)
            same_location = normalize_text(cand.location) == normalize_text(item.location)
            if same_deadline and same_location:
                opp, alt_source = cand, True
                break

    action = "unchanged"
    changes: list[str] = []
    if opp is None:
        opp = Opportunity(
            **data,
            title_norm=title_norm,
            organization_norm=org_norm,
            canonical_url=canonical,
            external_id=item.external_id,
            primary_source_id=source.id,
            content_hash=new_hash,
            first_seen_at=now,
            last_seen_at=now,
            last_verified_at=now if item.is_official else None,
            verification_status="verified" if item.is_official else "unverified",
            status="open",
        )
        db.add(opp)
        db.flush()
        action = "created"
    else:
        opp.last_seen_at = now
        is_primary = opp.primary_source_id == source.id and not alt_source
        primary_official = opp.verification_status == "verified"
        # Une source non officielle n'écrase jamais les données issues d'une source officielle.
        may_overwrite = is_primary or (item.is_official and not primary_official)
        if item.is_official:
            opp.last_verified_at = now
            opp.verification_status = "verified"
        if opp.status == "closed" and is_primary:
            opp.status = "open"
            changes.append("status")
        if may_overwrite and opp.content_hash != new_hash:
            for key in SIGNIFICANT_FIELDS:
                if getattr(opp, key) != data.get(key):
                    changes.append(key)
            for key, value in data.items():
                setattr(opp, key, value)
            opp.title_norm, opp.organization_norm = title_norm, org_norm
            if not alt_source:
                opp.canonical_url = canonical
            opp.content_hash = new_hash
            opp.content_changed_at = now
            if item.is_official and not primary_official:
                opp.primary_source_id = source.id
                opp.external_id = item.external_id
            action = "updated"
        elif alt_source:
            action = "linked"
        if changes:
            opp.significant_change_at = now
            opp.significant_change_fields = sorted(set(changes))

    stmt = insert(OpportunitySource).values(
        opportunity_id=opp.id,
        source_id=source.id,
        # URL propre à l'annonce sur cette source (une page de liste serait partagée par plusieurs annonces).
        source_url=item.official_url,
        external_id=item.external_id,
        raw={**item.raw, "listing_url": item.source_url},
        first_seen_at=now,
        last_seen_at=now,
    )
    db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_opportunity_sources_source_url",
            set_={"last_seen_at": now, "raw": stmt.excluded.raw, "opportunity_id": opp.id},
        )
    )
    return UpsertResult(action=action, opportunity_id=opp.id, significant_changes=changes)


def _prepare(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("opens_at"), datetime):
        raw = {**raw, "opens_at": raw["opens_at"].date()}
    return raw


def dry_run_source(source: Source, http: PoliteClient | None = None, sample_size: int = 5) -> dict[str, Any]:
    """Essai à blanc : interroge la source et valide les annonces SANS rien enregistrer."""
    started = time.monotonic()
    errors: list[str] = []
    sample: list[dict[str, Any]] = []
    found = 0
    own = http is None
    http = http or PoliteClient(min_delay=source.rate_limit_seconds)
    connector = None
    try:
        connector = build_connector(source, http)
        connector.max_items = min(connector.max_items, 50)
        for raw in connector.fetch():
            try:
                item = NormalizedOpportunity.model_validate(_prepare(raw))
            except ValidationError as exc:
                errors.append(f"{str(raw.get('title'))[:80]} : {exc.errors()[0]['msg']}")
                continue
            found += 1
            if len(sample) < sample_size:
                sample.append(
                    {
                        "title": item.title,
                        "organization": item.organization,
                        "type": item.type.value,
                        "official_url": item.official_url,
                        "countries": item.countries,
                        "deadline_status": item.deadline_status.value,
                    }
                )
    except (ConnectorError, ValueError) as exc:
        errors.append(str(exc))
    finally:
        if own:
            http.close()
    if connector is not None:
        # Détail par élément (board, flux…) même quand la source échoue globalement.
        errors.extend(f"{i.item} : {i.error}" for i in connector.issues)
    return {
        "ok": found > 0,
        "items_found": found,
        "sample": sample,
        "errors": errors[:20],
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def run_source(
    db: Session, source: Source, *, triggered_by: str = "cron", http: PoliteClient | None = None
) -> IngestionRun:
    run = IngestionRun(source_id=source.id, job_name="collect", triggered_by=triggered_by, status="running")
    db.add(run)
    source.last_run_at = utcnow()
    db.commit()
    log_event(logger, "source run start", source=source.key, run_id=str(run.id))

    own = http is None
    http = http or PoliteClient(min_delay=source.rate_limit_seconds)
    errors: list[dict[str, str]] = []
    changed_ids: list[str] = []
    fatal: str | None = None
    connector = None
    try:
        connector = build_connector(source, http)
        for raw in connector.fetch():
            run.items_fetched += 1
            try:
                item = NormalizedOpportunity.model_validate(_prepare(raw))
            except ValidationError as exc:
                run.items_skipped += 1
                errors.append({"item": str(raw.get("title"))[:120], "error": exc.errors()[0]["msg"]})
                continue
            try:
                with db.begin_nested():
                    result = upsert_opportunity(db, source, item)
            except Exception as exc:  # une annonce défectueuse n'interrompt pas la collecte
                run.items_skipped += 1
                errors.append({"item": item.title[:120], "error": exc.__class__.__name__})
                logger.exception("upsert failed")
                continue
            if result.action == "created":
                run.items_created += 1
            elif result.action == "updated":
                run.items_updated += 1
            else:
                run.items_unchanged += 1
            if result.significant_changes:
                changed_ids.append(str(result.opportunity_id))
            if run.items_fetched % 25 == 0:
                db.commit()
    except AccessDenied as exc:
        fatal = str(exc)
    except ConnectorError as exc:
        fatal = str(exc)
    except Exception as exc:  # erreur de code inattendue : journalisée, autres sources poursuivies
        logger.exception("connector crashed")
        fatal = f"Erreur interne du connecteur : {exc.__class__.__name__}"
    finally:
        if own:
            http.close()
    if connector is not None:
        errors.extend({"item": i.item, "error": i.error} for i in connector.issues)

    now = utcnow()
    run.finished_at = now
    run.errors_count = len(errors) + (1 if fatal else 0)
    run.details = {
        "errors": errors[:50],
        "fatal": fatal,
        "significant_changes": changed_ids[:100],
        "truncated": bool(connector and connector.truncated),
    }
    if fatal:
        run.status = "failed"
        source.consecutive_failures += 1
        source.last_error = fatal[:1000]
        if source.consecutive_failures >= 3:
            source.verification_status = "failing"
    else:
        run.status = "partial" if errors else "success"
        source.consecutive_failures = 0
        source.last_success_at = now
        source.last_error = errors[0]["error"][:1000] if errors else None
        if run.items_fetched > 0 and source.verification_status != "verified":
            source.verification_status = "verified"
        # Annonces disparues d'une liste complète : marquées closes (jamais supprimées).
        if connector and connector.complete_listing and not errors and not connector.truncated:
            closed = db.execute(
                update(Opportunity)
                .where(
                    Opportunity.primary_source_id == source.id,
                    Opportunity.last_seen_at < run.started_at,
                    Opportunity.status == "open",
                )
                .values(status="closed", significant_change_at=now, significant_change_fields=["status"])
            ).rowcount
            run.details = {**run.details, "closed": closed or 0}
    db.commit()
    log_event(
        logger,
        "source run end",
        source=source.key,
        status=run.status,
        fetched=run.items_fetched,
        created=run.items_created,
        updated=run.items_updated,
        errors=run.errors_count,
    )
    return run
