"""Administration (réservée à l'administrateur authentifié) : sources, collectes, jobs, aperçus."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession
from app.core.config import get_settings
from app.core.errors import Conflict, NotFound, TooManyRequests
from app.core.timeutil import utcnow
from app.db.locks import LockNotAcquired, job_lock
from app.db.session import session_scope
from app.models import IngestionRun, Opportunity, Source, User
from app.schemas.auth import AdminUserOut, AdminUserUpdate
from app.schemas.misc import IngestionRunOut, SourceOut, SourceTestOut, SourceUpdate
from app.services import auth as auth_service
from app.services import matching
from app.services.link_import import MANUAL_CONNECTOR
from app.workers.connectors.registry import CONNECTORS
from app.workers.ingestion import dry_run_source
from app.workers.notifications import service as notif

router = APIRouter(prefix="/admin", tags=["administration"])
logger = logging.getLogger("app.admin")
TEST_COOLDOWN = timedelta(seconds=60)


def _source(db, source_id: uuid.UUID) -> Source:  # type: ignore[no-untyped-def]
    src = db.get(Source, source_id)
    if src is None or src.connector == MANUAL_CONNECTOR:
        raise NotFound("Source introuvable.")
    return src


def _out(db, src: Source) -> SourceOut:  # type: ignore[no-untyped-def]
    out = SourceOut.model_validate(src)
    out.opportunities_count = (
        db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.primary_source_id == src.id)) or 0
    )
    return out


@router.get("/sources", response_model=list[SourceOut])
def list_sources(_: AdminUser, db: DbSession) -> list[SourceOut]:
    # Les ajouts manuels ne sont pas une source de collecte (ni test, ni collecte, ni configuration).
    rows = db.scalars(select(Source).where(Source.connector != MANUAL_CONNECTOR).order_by(Source.key))
    return [_out(db, s) for s in rows]


@router.get("/connectors")
def list_connectors(_: AdminUser) -> dict[str, Any]:
    return {
        name: {"official": cls.official, "complete_listing": cls.complete_listing} for name, cls in CONNECTORS.items()
    }


@router.patch("/sources/{source_id}", response_model=SourceOut)
def update_source(source_id: uuid.UUID, data: SourceUpdate, _: AdminUser, db: DbSession) -> SourceOut:
    src = _source(db, source_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(src, key, value)
    db.commit()
    return _out(db, src)


@router.post(
    "/sources/{source_id}/test", response_model=SourceTestOut, summary="Essai à blanc (aucune écriture d'annonce)"
)
def test(source_id: uuid.UUID, _: AdminUser, db: DbSession) -> SourceTestOut:
    src = _source(db, source_id)
    if src.last_tested_at and utcnow() - src.last_tested_at < TEST_COOLDOWN:
        raise TooManyRequests("Patientez une minute entre deux tests de la même source.")
    src.last_tested_at = utcnow()
    db.commit()
    result = dry_run_source(src)
    if result["ok"]:
        src.verification_status = "verified"
    elif result["errors"]:
        src.last_error = result["errors"][0][:1000]
    db.commit()
    return SourceTestOut(source_key=src.key, verification_status=src.verification_status, **result)


def _collect_in_background(source_key: str | None) -> None:
    from app.jobs.collect_opportunities import collect

    with session_scope() as db:
        try:
            with job_lock(db, "collect_opportunities", timedelta(hours=2)):
                collect(db, source_key, triggered_by="admin")
        except LockNotAcquired:
            logger.warning("admin collect skipped: already running")


class CollectAccepted(BaseModel):
    message: str
    source: str | None


@router.post(
    "/collect",
    response_model=CollectAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Déclenche une collecte (protégée : admin, verrou et délai minimal)",
)
def trigger_collect(
    _: AdminUser, db: DbSession, background: BackgroundTasks, source_id: uuid.UUID | None = None
) -> CollectAccepted:
    cooldown = timedelta(minutes=get_settings().admin_collect_cooldown_minutes)
    recent = db.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(IngestionRun.triggered_by == "admin", IngestionRun.started_at >= utcnow() - cooldown)
    )
    if recent:
        raise TooManyRequests(
            f"Une collecte manuelle a déjà été lancée il y a moins de {cooldown.seconds // 60} minutes."
        )
    running = db.scalar(
        select(func.count())
        .select_from(IngestionRun)
        .where(IngestionRun.status == "running", IngestionRun.started_at >= utcnow() - timedelta(hours=2))
    )
    if running:
        raise Conflict("Une collecte est déjà en cours.")
    key = _source(db, source_id).key if source_id else None
    background.add_task(_collect_in_background, key)
    return CollectAccepted(message="Collecte lancée en arrière-plan.", source=key)


@router.get("/runs", response_model=list[IngestionRunOut])
def runs(_: AdminUser, db: DbSession, source_id: uuid.UUID | None = None, limit: int = 30) -> list[IngestionRunOut]:
    q = select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(min(max(limit, 1), 200))
    if source_id:
        q = q.where(IngestionRun.source_id == source_id)
    return [IngestionRunOut.model_validate(r) for r in db.scalars(q)]


@router.post("/jobs/check-deadlines", summary="Exécute maintenant les rappels (dédupliqués)")
def run_check_deadlines(_: AdminUser, db: DbSession) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for user in db.scalars(select(User).where(User.is_active.is_(True))).all():
        out[str(user.id)] = {
            "deadlines": [o.status for o in notif.send_deadline_reminders(db, user)],
            "tasks": [o.status for o in notif.send_task_reminders(db, user)],
            "changes": [o.status for o in notif.send_change_alerts(db, user)],
        }
    return out


@router.post("/jobs/recompute-matches")
def run_recompute(_: AdminUser, db: DbSession, force: bool = False) -> dict[str, Any]:
    return {"recomputed": matching.recompute_all(db, force=force)}


@router.get("/users", response_model=list[AdminUserOut], summary="Comptes (inscriptions, confirmation, activité)")
def list_users(_: AdminUser, db: DbSession, limit: int = 200) -> list[AdminUserOut]:
    rows = db.scalars(select(User).order_by(User.created_at.desc()).limit(min(max(limit, 1), 500))).all()
    return [AdminUserOut.model_validate(u) for u in rows]


@router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Active ou désactive un compte")
def update_user(user_id: uuid.UUID, data: AdminUserUpdate, admin: AdminUser, db: DbSession) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("Compte introuvable.")
    if target.id == admin.id:
        raise Conflict("Vous ne pouvez pas désactiver votre propre compte.", code="self_update")
    target.is_active = data.is_active
    if not data.is_active:
        auth_service.revoke_all_sessions(db, target.id)
    db.commit()
    logger.info("user %s by admin", "enabled" if data.is_active else "disabled")
    return AdminUserOut.model_validate(target)
