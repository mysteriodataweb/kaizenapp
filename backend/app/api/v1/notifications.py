from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import NotificationLog
from app.schemas.misc import (
    NotificationLogOut,
    NotificationPrefsIn,
    NotificationPrefsOut,
    NotificationPreview,
    TestEmailIn,
)
from app.workers.notifications import service as notif
from app.workers.notifications.templates import render_items, render_simple

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _prefs_out(prefs, user) -> NotificationPrefsOut:  # type: ignore[no-untyped-def]
    out = NotificationPrefsOut.model_validate(prefs)
    out.email_mode = "resend" if get_settings().email_enabled else "simulation"
    out.effective_recipient = notif.effective_recipient(prefs, user)
    return out


@router.get("/preferences", response_model=NotificationPrefsOut)
def get_preferences(user: CurrentUser, db: DbSession) -> NotificationPrefsOut:
    prefs = notif.get_prefs(db, user)
    db.commit()
    return _prefs_out(prefs, user)


@router.put("/preferences", response_model=NotificationPrefsOut)
def put_preferences(data: NotificationPrefsIn, user: CurrentUser, db: DbSession) -> NotificationPrefsOut:
    if data.email and not notif.recipient_allowed(data.email, user):
        hint = " ou une adresse listée dans ALERT_RECIPIENT / EMAIL_ALLOWED_RECIPIENTS" if user.is_admin else ""
        raise AppError(
            f"Adresse non autorisée : utilisez l'e-mail de votre compte{hint}.",
            code="recipient_not_allowed",
            status_code=422,
        )
    prefs = notif.get_prefs(db, user)
    for key, value in data.model_dump().items():
        setattr(prefs, key, value.value if hasattr(value, "value") else value)
    db.commit()
    return _prefs_out(prefs, user)


@router.get("/logs", response_model=list[NotificationLogOut])
def logs(user: CurrentUser, db: DbSession, limit: int = 50) -> list[NotificationLogOut]:
    rows = db.scalars(
        select(NotificationLog)
        .where(NotificationLog.user_id == user.id)
        .order_by(NotificationLog.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    return [NotificationLogOut.model_validate(r) for r in rows]


@router.get("/preview", response_model=NotificationPreview, summary="Aperçu d'un e-mail sans l'envoyer")
def preview(
    user: CurrentUser, db: DbSession, kind: Literal["digest", "new_matches", "deadline"] = "digest"
) -> NotificationPreview:
    prefs = notif.get_prefs(db, user)
    if kind == "digest":
        title, html, text, payload = notif.build_digest(db, user, prefs)
        return NotificationPreview(
            kind=kind,
            subject=f"[OI] {title}",
            html=html,
            text=text,
            items=len(payload["top"]) + len(payload["deadlines"]),
        )
    if kind == "new_matches":
        rows = notif.candidate_new_matches(db, user, prefs)[: prefs.max_items]
        items = [notif._item(o, m) for o, m in rows]
        html, text = render_items(
            f"{len(items)} nouvelle(s) opportunité(s)", "Aperçu (non envoyé).", items, user.timezone
        )
        return NotificationPreview(
            kind=kind,
            subject="[OI] Nouvelles opportunités",
            html=html,
            text=text,
            items=len(items),
            note=None if items else "Aucune nouvelle opportunité non encore notifiée.",
        )
    due = notif.due_deadline_reminders(db, user, prefs)
    items = []
    for opp, deadline, status, threshold, _left in due:
        item = notif._item(opp, None, note=f"Rappel J-{threshold}")
        item.deadline_at, item.deadline_status = deadline, status
        items.append(item)
    html, text = render_items("Rappels d'échéance dus", "Aperçu (non envoyé).", items, user.timezone)
    return NotificationPreview(
        kind=kind,
        subject="[OI] Rappels",
        html=html,
        text=text,
        items=len(items),
        note=None if items else "Aucun rappel dû aujourd'hui (les dates inconnues ne génèrent jamais de rappel).",
    )


@router.post("/test", response_model=NotificationLogOut, summary="Envoie un e-mail de test à l'adresse autorisée")
def send_test(data: TestEmailIn, user: CurrentUser, db: DbSession) -> NotificationLogOut:
    if not data.confirm:
        raise AppError("Confirmation explicite requise (confirm=true).", code="confirmation_required", status_code=422)
    html, text = render_simple(
        "E-mail de test", ["Ce message confirme que les alertes d'Opportunity Intelligence vous parviennent."]
    )
    outcome = notif.dispatch(
        db,
        user,
        kind="test",
        dedup_key=f"test:{utcnow().strftime('%Y%m%d%H%M')}",
        subject="[OI] E-mail de test",
        html=html,
        text=text,
    )
    if outcome.log_id is None:
        raise AppError(
            "Aucune adresse autorisée configurée pour l'envoi.", code="recipient_not_allowed", status_code=422
        )
    log = db.get(NotificationLog, outcome.log_id)
    return NotificationLogOut.model_validate(log)
