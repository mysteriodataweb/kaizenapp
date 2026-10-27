"""Construction et envoi dédupliqué des notifications.

Garanties :
  * (user_id, dedup_key) unique en base : une notification logique n'est envoyée qu'une fois ;
  * la ligne de journal est validée AVANT l'appel au fournisseur (pas de double envoi en cas de crash,
    et clé d'idempotence Resend en complément) ;
  * aucun rappel n'est envoyé pour une date inconnue ; une date non vérifiée est signalée comme telle ;
  * seuls le compte de l'utilisateur et les adresses autorisées peuvent recevoir des e-mails.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.core.timeutil import days_until, safe_zone, utcnow
from app.models import (
    Application,
    Favorite,
    Match,
    NotificationLog,
    NotificationPreference,
    Opportunity,
    Source,
    Task,
    User,
)
from app.models.enums import ACTIVE_APPLICATION_STATUSES
from app.workers.notifications.email import EmailMessage, get_email_client
from app.workers.notifications.templates import EmailItem, render_items, render_simple

logger = logging.getLogger("app.notifications")
MAX_ATTEMPTS = 3
STALE_PENDING = timedelta(minutes=15)


@dataclass
class Outcome:
    status: str  # sent | simulated | failed | duplicate | skipped
    log_id: Any = None


def get_prefs(db: Session, user: User) -> NotificationPreference:
    prefs = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == user.id))
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id, email=user.email)
        db.add(prefs)
        db.flush()
    return prefs


def recipient_allowed(email: str | None, user: User) -> bool:
    if not email:
        return False
    email = email.strip().lower()
    return email == user.email.lower() or email in get_settings().allowed_recipients


def effective_recipient(prefs: NotificationPreference, user: User) -> str | None:
    candidate = prefs.email or user.email
    return candidate if recipient_allowed(candidate, user) else None


def dispatch(
    db: Session,
    user: User,
    *,
    kind: str,
    dedup_key: str,
    subject: str,
    html: str,
    text: str,
    payload: dict[str, Any] | None = None,
    recipient: str | None = None,
) -> Outcome:
    prefs = get_prefs(db, user)
    to = recipient or effective_recipient(prefs, user)
    client = get_email_client()
    if not to:
        log_event(logger, "notification skipped: recipient not allowed", logging.WARNING, kind=kind)
        return Outcome("skipped")

    existing = db.scalar(
        select(NotificationLog).where(NotificationLog.user_id == user.id, NotificationLog.dedup_key == dedup_key)
    )
    if existing is not None:
        retryable = existing.status == "failed" and existing.attempts < MAX_ATTEMPTS
        stale = existing.status == "pending" and existing.created_at < utcnow() - STALE_PENDING
        if not (retryable or stale):
            return Outcome("duplicate", existing.id)
        log = existing
    else:
        result = db.execute(
            insert(NotificationLog)
            .values(
                user_id=user.id,
                kind=kind,
                dedup_key=dedup_key,
                recipient=to,
                subject=subject[:300],
                status="pending",
                provider=client.provider,
                payload=payload or {},
            )
            .on_conflict_do_nothing(constraint="uq_notification_logs_dedup")
            .returning(NotificationLog.id)
        ).first()
        db.commit()
        if result is None:  # course avec une autre exécution
            return Outcome("duplicate")
        log = db.get(NotificationLog, result[0])
        assert log is not None

    log.attempts += 1
    log.provider = client.provider
    db.commit()
    res = client.send(
        EmailMessage(to=to, subject=subject, html=html, text=text, idempotency_key=f"{user.id}:{dedup_key}")
    )
    log.status = res.status
    log.provider_message_id = res.message_id
    log.last_error = res.error
    if res.status in ("sent", "simulated"):
        log.sent_at = utcnow()
    elif not res.retryable:
        log.attempts = MAX_ATTEMPTS
    db.commit()
    log_event(logger, "notification processed", kind=kind, status=res.status, provider=client.provider)
    return Outcome(res.status, log.id)


def _hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(parts)).encode()).hexdigest()[:24]


def _item(opp: Opportunity, match: Match | None, note: str | None = None) -> EmailItem:
    reasons: list[str] = []
    if match:
        expl = match.explanation or {}
        reasons = (
            (expl.get("satisfied") or [])[:2] + (expl.get("unsatisfied") or [])[:1] + (expl.get("unknown") or [])[:1]
        )
    return EmailItem(
        opportunity_id=str(opp.id),
        title=opp.title,
        organization=opp.organization,
        type=opp.type,
        official_url=opp.official_url,
        deadline_at=opp.deadline_at,
        deadline_status=opp.deadline_status,
        eligibility=match.eligibility if match else None,
        score=match.score if match else None,
        confidence=match.confidence if match else None,
        reasons=reasons,
        note=note,
    )


# ------------------------------------------------------------------ nouvelles opportunités
def candidate_new_matches(db: Session, user: User, prefs: NotificationPreference) -> list[tuple[Opportunity, Match]]:
    now = utcnow()
    rows = db.execute(
        select(Opportunity, Match)
        .join(Match, and_(Match.opportunity_id == Opportunity.id, Match.user_id == user.id))
        .where(
            Match.notified_at.is_(None),
            Match.score >= prefs.min_score,
            Match.eligibility != "ineligible",
            Opportunity.status != "closed",
            or_(Opportunity.deadline_at.is_(None), Opportunity.deadline_at >= now),
        )
        .order_by(Match.score.desc())
    ).all()
    return [(o, m) for o, m in rows]


def send_new_matches(db: Session, user: User) -> Outcome:
    prefs = get_prefs(db, user)
    if not (prefs.enabled and prefs.notify_new_matches):
        return Outcome("skipped")
    rows = candidate_new_matches(db, user, prefs)
    if not rows:
        return Outcome("skipped")
    shown = rows[: prefs.max_items]
    items = [_item(o, m) for o, m in shown]
    extra = f"<p>… et {len(rows) - len(shown)} autre(s) dans l'application.</p>" if len(rows) > len(shown) else ""
    html, text = render_items(
        f"{len(rows)} nouvelle(s) opportunité(s) pour vous",
        f"Opportunités avec une compatibilité ≥ {prefs.min_score}/100, non inéligibles.",
        items,
        user.timezone,
        extra,
    )
    key = "new_matches:" + _hash([str(o.id) for o, _ in rows])
    outcome = dispatch(
        db,
        user,
        kind="new_matches",
        dedup_key=key,
        subject=f"[OI] {len(rows)} nouvelle(s) opportunité(s)",
        html=html,
        text=text,
        payload={"opportunity_ids": [str(o.id) for o, _ in shown], "total": len(rows)},
    )
    if outcome.status in ("sent", "simulated", "duplicate"):
        now = utcnow()
        for _, m in rows:
            m.notified_at = now
        db.commit()
    return outcome


# ------------------------------------------------------------------ récapitulatif
def digest_period(prefs: NotificationPreference, tz: str, now: datetime | None = None) -> str | None:
    """Clé de période si un récapitulatif est dû maintenant (heure/jour locaux), sinon None."""
    now = now or utcnow()
    local = now.astimezone(safe_zone(tz))
    if prefs.digest_frequency == "never" or local.hour < prefs.digest_hour:
        return None
    if prefs.digest_frequency == "daily":
        return local.strftime("daily:%Y-%m-%d")
    if local.weekday() != prefs.digest_weekday:
        return None
    year, week, _ = local.isocalendar()
    return f"weekly:{year}-W{week:02d}"


def build_digest(db: Session, user: User, prefs: NotificationPreference) -> tuple[str, str, str, dict[str, Any]]:
    now = utcnow()
    top = db.execute(
        select(Opportunity, Match)
        .join(Match, and_(Match.opportunity_id == Opportunity.id, Match.user_id == user.id))
        .where(
            Match.score >= prefs.min_score,
            Match.eligibility != "ineligible",
            Opportunity.status != "closed",
            or_(Opportunity.deadline_at.is_(None), Opportunity.deadline_at >= now),
        )
        .order_by(Match.score.desc())
        .limit(prefs.max_items)
    ).all()
    upcoming = db.execute(
        select(Application, Opportunity)
        .join(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(
            Application.user_id == user.id,
            Application.status.in_([s.value for s in ACTIVE_APPLICATION_STATUSES]),
            Opportunity.deadline_at.is_not(None),
            Opportunity.deadline_at >= now,
            Opportunity.deadline_at <= now + timedelta(days=30),
        )
        .order_by(Opportunity.deadline_at)
        .limit(10)
    ).all()
    overdue = db.scalars(
        select(Task).where(Task.user_id == user.id, Task.status.in_(("todo", "in_progress")), Task.due_at < now)
    ).all()
    matches = {m.opportunity_id: m for m in db.scalars(select(Match).where(Match.user_id == user.id))}
    items = [_item(o, m) for o, m in top]
    deadline_items = [_item(o, matches.get(o.id), note="Candidature suivie") for _, o in upcoming]
    period = "de la semaine" if prefs.digest_frequency == "weekly" else "du jour"
    title = f"Votre récapitulatif {period}"
    intro = (
        f"{len(items)} opportunité(s) compatibles, {len(deadline_items)} échéance(s) suivie(s) sous 30 jours, "
        f"{len(overdue)} tâche(s) en retard."
    )
    html, text = render_items(title, intro, items + deadline_items, user.timezone)
    payload = {
        "top": [str(o.id) for o, _ in top],
        "deadlines": [str(o.id) for _, o in upcoming],
        "overdue_tasks": len(overdue),
    }
    return title, html, text, payload


def send_digest(db: Session, user: User, now: datetime | None = None, force_period: str | None = None) -> Outcome:
    prefs = get_prefs(db, user)
    if not prefs.enabled:
        return Outcome("skipped")
    period = force_period or digest_period(prefs, user.timezone, now)
    if period is None:
        return Outcome("skipped")
    title, html, text, payload = build_digest(db, user, prefs)
    outcome = dispatch(
        db,
        user,
        kind="digest",
        dedup_key=f"digest:{period}",
        subject=f"[OI] {title}",
        html=html,
        text=text,
        payload=payload,
    )
    if outcome.status in ("sent", "simulated"):
        prefs.last_digest_sent_at = utcnow()
        db.commit()
    return outcome


# ------------------------------------------------------------------ rappels d'échéance
def due_deadline_reminders(db: Session, user: User, prefs: NotificationPreference, now: datetime | None = None):  # type: ignore[no-untyped-def]
    """Rappels dus : (opportunité, échéance, statut de date, seuil J-n). Jamais pour une date inconnue."""
    now = now or utcnow()
    thresholds = sorted(prefs.deadline_reminder_days or [])
    if not thresholds:
        return []
    tracked = db.execute(
        select(Opportunity, Application)
        .join(Application, Application.opportunity_id == Opportunity.id)
        .where(Application.user_id == user.id, Application.status.in_([s.value for s in ACTIVE_APPLICATION_STATUSES]))
    ).all()
    favorites = (
        db.execute(
            select(Opportunity)
            .join(Favorite, Favorite.opportunity_id == Opportunity.id)
            .outerjoin(Application, and_(Application.opportunity_id == Opportunity.id, Application.user_id == user.id))
            .where(Favorite.user_id == user.id, Application.id.is_(None))
        )
        .scalars()
        .all()
    )
    out = []
    for opp, app in [*tracked, *[(f, None) for f in favorites]]:
        if app is not None and app.deadline_at is not None:
            deadline, status = app.deadline_at, "confirmed"
        elif opp.deadline_at is not None and opp.deadline_status in ("confirmed", "unverified"):
            deadline, status = opp.deadline_at, opp.deadline_status
        else:
            continue  # date inconnue : aucun rappel
        left = days_until(deadline, user.timezone, now)
        if left < 0:
            continue
        due = [t for t in thresholds if left <= t]
        if not due:
            continue
        out.append((opp, deadline, status, min(due), left))
    return out


def send_deadline_reminders(db: Session, user: User, now: datetime | None = None) -> list[Outcome]:
    prefs = get_prefs(db, user)
    if not (prefs.enabled and prefs.notify_deadlines):
        return []
    matches = {m.opportunity_id: m for m in db.scalars(select(Match).where(Match.user_id == user.id))}
    outcomes = []
    for opp, deadline, status, threshold, left in due_deadline_reminders(db, user, prefs, now):
        unverified = status == "unverified"
        note = "Attention : cette date n'est PAS vérifiée. Confirmez-la sur le site officiel." if unverified else None
        item = _item(opp, matches.get(opp.id), note=note)
        item.deadline_at, item.deadline_status = deadline, status
        when = "aujourd'hui" if left == 0 else f"dans {left} jour(s)"
        title = f"Échéance {when} : {opp.title}"
        html, text = render_items(title, f"Rappel J-{threshold}.", [item], user.timezone)
        subject = f"[OI] J-{threshold}{' (date non vérifiée)' if unverified else ''} : {opp.title}"[:300]
        key = f"deadline:{opp.id}:{deadline.date().isoformat()}:J-{threshold}"
        outcomes.append(
            dispatch(
                db,
                user,
                kind="deadline",
                dedup_key=key,
                subject=subject,
                html=html,
                text=text,
                payload={"opportunity_id": str(opp.id), "threshold": threshold, "date_status": status},
            )
        )
    return outcomes


# ------------------------------------------------------------------ tâches
def send_task_reminders(db: Session, user: User, now: datetime | None = None) -> list[Outcome]:
    prefs = get_prefs(db, user)
    if not (prefs.enabled and prefs.notify_tasks):
        return []
    now = now or utcnow()
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.status.in_(("todo", "in_progress")),
            Task.due_at.is_not(None),
            Task.due_at <= now + timedelta(hours=24),
        )
    ).all()
    outcomes = []
    for task in tasks:
        assert task.due_at is not None
        late = task.due_at < now
        local = task.due_at.astimezone(safe_zone(user.timezone)).strftime("%d/%m/%Y %H:%M")
        title = ("Tâche en retard : " if late else "Tâche à faire : ") + task.title
        html, text = render_simple(
            title,
            [f"Échéance : {local}.", task.description or ""],
            ("Voir mes tâches", f"{get_settings().frontend_url}/calendar"),
        )
        key = f"task:{task.id}:{task.due_at.date().isoformat()}:{'late' if late else 'due'}"
        outcomes.append(
            dispatch(
                db,
                user,
                kind="task",
                dedup_key=key,
                subject=f"[OI] {title}"[:300],
                html=html,
                text=text,
                payload={"task_id": str(task.id)},
            )
        )
    return outcomes


# ------------------------------------------------------------------ modifications significatives
FIELD_LABELS = {
    "deadline_at": "date limite",
    "deadline_status": "statut de la date",
    "funding_type": "financement",
    "funding_amount": "montant",
    "eligible_nationalities": "nationalités admises",
    "study_levels": "niveaux admis",
    "required_languages": "langues exigées",
    "required_documents": "documents exigés",
    "title": "titre",
    "official_url": "lien officiel",
    "status": "statut (ouverte/fermée)",
}


def send_change_alerts(db: Session, user: User) -> list[Outcome]:
    prefs = get_prefs(db, user)
    if not (prefs.enabled and prefs.notify_changes):
        return []
    rows = db.execute(
        select(Opportunity, Application.created_at)
        .outerjoin(Application, and_(Application.opportunity_id == Opportunity.id, Application.user_id == user.id))
        .outerjoin(Favorite, and_(Favorite.opportunity_id == Opportunity.id, Favorite.user_id == user.id))
        .where(
            Opportunity.significant_change_at.is_not(None),
            or_(Application.id.is_not(None), Favorite.user_id.is_not(None)),
        )
    ).all()
    matches = {m.opportunity_id: m for m in db.scalars(select(Match).where(Match.user_id == user.id))}
    outcomes = []
    for opp, tracked_since in rows:
        if tracked_since is not None and opp.significant_change_at and opp.significant_change_at < tracked_since:
            continue
        labels = ", ".join(FIELD_LABELS.get(f, f) for f in opp.significant_change_fields) or "informations"
        item = _item(opp, matches.get(opp.id), note=f"Modifié : {labels}.")
        html, text = render_items(
            f"Mise à jour : {opp.title}", "Une opportunité que vous suivez a changé.", [item], user.timezone
        )
        key = f"change:{opp.id}:{opp.content_hash[:16]}:{opp.status}"
        outcomes.append(
            dispatch(
                db,
                user,
                kind="change",
                dedup_key=key,
                subject=f"[OI] Modifiée : {opp.title}"[:300],
                html=html,
                text=text,
                payload={"opportunity_id": str(opp.id), "fields": opp.significant_change_fields},
            )
        )
    return outcomes


# ------------------------------------------------------------------ erreurs de collecte
def send_ingestion_alerts(db: Session, threshold: int = 3) -> list[Outcome]:
    failing = db.scalars(select(Source).where(Source.enabled.is_(True), Source.consecutive_failures >= threshold)).all()
    if not failing:
        return []
    outcomes = []
    for admin in db.scalars(select(User).where(User.is_admin.is_(True), User.is_active.is_(True))).all():
        prefs = get_prefs(db, admin)
        if not (prefs.enabled and prefs.notify_ingestion_errors):
            continue
        for src in failing:
            streak = src.last_success_at.date().isoformat() if src.last_success_at else "jamais"
            html, text = render_simple(
                f"Collecte en échec : {src.name}",
                [
                    f"{src.consecutive_failures} échecs consécutifs (dernier succès : {streak}).",
                    f"Dernière erreur : {src.last_error or 'inconnue'}",
                    "Les autres sources continuent d'être collectées.",
                ],
                ("Gérer les sources", f"{get_settings().frontend_url}/admin/sources"),
            )
            outcomes.append(
                dispatch(
                    db,
                    admin,
                    kind="ingestion_error",
                    dedup_key=f"ingest_error:{src.id}:{streak}",
                    subject=f"[OI] Collecte en échec : {src.name}"[:300],
                    html=html,
                    text=text,
                    payload={"source": src.key, "failures": src.consecutive_failures},
                )
            )
    return outcomes
