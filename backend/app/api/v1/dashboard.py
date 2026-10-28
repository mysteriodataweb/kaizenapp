from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.timeutil import utcnow
from app.models import Application, Favorite, IngestionRun, Match, NotificationLog, Opportunity, Source, Task
from app.models.enums import ACTIVE_APPLICATION_STATUSES
from app.services.applications import list_applications

router = APIRouter(tags=["tableau de bord"])


class DashboardOut(BaseModel):
    generated_at: datetime
    last_visit_at: datetime | None
    opportunities_total: int
    opportunities_by_type: dict[str, int]
    new_since_last_visit: int
    eligible: int
    eligibility_unknown: int
    ineligible: int
    applications_by_status: dict[str, int]
    applications_in_progress: int
    applications_submitted: int
    deadlines_7_days: int
    deadlines_30_days: int
    upcoming: list[dict[str, Any]]
    overdue_tasks: list[dict[str, Any]]
    favorites: int
    latest_runs: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    latest_emails: list[dict[str, Any]]
    recent_errors: list[dict[str, Any]]


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: CurrentUser, db: DbSession) -> DashboardOut:
    now = utcnow()
    open_cond = and_(
        Opportunity.status != "closed", or_(Opportunity.deadline_at.is_(None), Opportunity.deadline_at >= now)
    )
    by_type = dict(db.execute(select(Opportunity.type, func.count()).where(open_cond).group_by(Opportunity.type)).all())
    since = user.previous_seen_at
    new_count = (
        db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.first_seen_at > since))
        if since
        else db.scalar(select(func.count()).select_from(Opportunity))
    )
    elig = dict(
        db.execute(
            select(Match.eligibility, func.count())
            .join(Opportunity, Opportunity.id == Match.opportunity_id)
            .where(Match.user_id == user.id, open_cond)
            .group_by(Match.eligibility)
        ).all()
    )
    by_status = dict(
        db.execute(
            select(Application.status, func.count()).where(Application.user_id == user.id).group_by(Application.status)
        ).all()
    )
    apps = [a for a in list_applications(db, user) if a.status in [s.value for s in ACTIVE_APPLICATION_STATUSES]]
    upcoming = []
    for a in apps:
        deadline = a.deadline_at or a.opportunity.deadline_at
        if deadline and now <= deadline <= now + timedelta(days=30):
            upcoming.append(
                {
                    "application_id": str(a.id),
                    "opportunity_id": str(a.opportunity.id),
                    "title": a.opportunity.title,
                    "organization": a.opportunity.organization,
                    "deadline_at": deadline.isoformat(),
                    "deadline_status": "confirmed" if a.deadline_at else a.opportunity.deadline_status,
                    "status": a.status,
                    "urgency": a.urgency.model_dump() if a.urgency else None,
                }
            )
    upcoming.sort(key=lambda x: x["deadline_at"])
    overdue = (
        db.execute(
            select(Task)
            .where(Task.user_id == user.id, Task.status.in_(("todo", "in_progress")), Task.due_at < now)
            .order_by(Task.due_at)
            .limit(10)
        )
        .scalars()
        .all()
    )
    runs = db.execute(
        select(IngestionRun, Source.name)
        .outerjoin(Source, Source.id == IngestionRun.source_id)
        .order_by(IngestionRun.started_at.desc())
        .limit(6)
    ).all()
    sources = db.scalars(select(Source).where(Source.connector != "manual").order_by(Source.key)).all()
    emails = db.scalars(
        select(NotificationLog)
        .where(NotificationLog.user_id == user.id)
        .order_by(NotificationLog.created_at.desc())
        .limit(5)
    ).all()
    # Détails techniques des collectes : réservés à l'administrateur.
    err_runs = (
        db.execute(
            select(IngestionRun, Source.name)
            .outerjoin(Source, Source.id == IngestionRun.source_id)
            .where(IngestionRun.status.in_(("failed", "partial")), IngestionRun.started_at >= now - timedelta(days=7))
            .order_by(IngestionRun.started_at.desc())
            .limit(5)
        ).all()
        if user.is_admin
        else []
    )
    err_mails = db.scalars(
        select(NotificationLog)
        .where(NotificationLog.user_id == user.id, NotificationLog.status == "failed")
        .order_by(NotificationLog.created_at.desc())
        .limit(5)
    ).all()
    return DashboardOut(
        generated_at=now,
        last_visit_at=since,
        opportunities_total=sum(by_type.values()),
        opportunities_by_type=by_type,
        new_since_last_visit=new_count or 0,
        eligible=elig.get("eligible", 0),
        eligibility_unknown=elig.get("unknown", 0),
        ineligible=elig.get("ineligible", 0),
        applications_by_status=by_status,
        applications_in_progress=sum(by_status.get(s.value, 0) for s in ACTIVE_APPLICATION_STATUSES),
        applications_submitted=sum(by_status.get(s, 0) for s in ("submitted", "selection")),
        deadlines_7_days=sum(1 for u in upcoming if u["deadline_at"] <= (now + timedelta(days=7)).isoformat()),
        deadlines_30_days=len(upcoming),
        upcoming=upcoming[:10],
        overdue_tasks=[
            {
                "id": str(t.id),
                "title": t.title,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "application_id": str(t.application_id) if t.application_id else None,
            }
            for t in overdue
        ],
        favorites=db.scalar(select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id)) or 0,
        latest_runs=[
            {
                "id": str(r.id),
                "source": name,
                "status": r.status,
                "started_at": r.started_at.isoformat(),
                "created": r.items_created,
                "updated": r.items_updated,
                "errors": r.errors_count,
            }
            for r, name in runs
        ],
        sources=[
            {
                "key": s.key,
                "name": s.name,
                "enabled": s.enabled,
                "verification_status": s.verification_status,
                "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
                "consecutive_failures": s.consecutive_failures,
            }
            for s in sources
        ],
        latest_emails=[
            {
                "id": str(e.id),
                "kind": e.kind,
                "subject": e.subject,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
            }
            for e in emails
        ],
        recent_errors=[
            {
                "type": "collecte",
                "source": name,
                "message": (r.details or {}).get("fatal") or f"{r.errors_count} erreur(s)",
                "at": r.started_at.isoformat(),
            }
            for r, name in err_runs
        ]
        + [
            {
                "type": "e-mail",
                "source": e.kind,
                "message": e.last_error or "Échec d'envoi",
                "at": e.created_at.isoformat(),
            }
            for e in err_mails
        ],
    )
