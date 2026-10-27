from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, select

from app.api.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import Application, Favorite, Opportunity, Task
from app.services.applications import list_applications

router = APIRouter(tags=["calendrier"])


class CalendarEvent(BaseModel):
    id: str
    kind: str  # deadline | favorite_deadline | task | next_action | follow_up
    title: str
    subtitle: str | None = None
    at: datetime
    deadline_status: str | None = None
    application_id: str | None = None
    opportunity_id: str | None = None
    status: str | None = None
    urgency: str | None = None
    overdue: bool = False


@router.get("/calendar", response_model=list[CalendarEvent], summary="Échéances, tâches et actions sur une période")
def calendar(
    user: CurrentUser, db: DbSession, start: datetime | None = None, end: datetime | None = None
) -> list[CalendarEvent]:
    now = utcnow()
    start = start or now - timedelta(days=7)
    end = end or now + timedelta(days=60)
    if end <= start or end - start > timedelta(days=400):
        raise AppError("Période invalide (400 jours maximum).", code="invalid_range", status_code=422)
    events: list[CalendarEvent] = []
    for a in list_applications(db, user):
        deadline = a.deadline_at or a.opportunity.deadline_at
        if deadline and start <= deadline <= end:
            events.append(
                CalendarEvent(
                    id=f"deadline:{a.id}",
                    kind="deadline",
                    title=a.opportunity.title,
                    subtitle=a.opportunity.organization,
                    at=deadline,
                    deadline_status="confirmed" if a.deadline_at else a.opportunity.deadline_status,
                    application_id=str(a.id),
                    opportunity_id=str(a.opportunity.id),
                    status=a.status,
                    urgency=a.urgency.level if a.urgency else None,
                )
            )
        for kind, when, label in (
            ("next_action", a.next_action_at, a.next_action),
            ("follow_up", a.follow_up_at, "Relance"),
        ):
            if when and start <= when <= end:
                events.append(
                    CalendarEvent(
                        id=f"{kind}:{a.id}",
                        kind=kind,
                        title=label or "Prochaine action",
                        subtitle=a.opportunity.title,
                        at=when,
                        application_id=str(a.id),
                        opportunity_id=str(a.opportunity.id),
                        status=a.status,
                        overdue=when < now,
                    )
                )
    favs = db.scalars(
        select(Opportunity)
        .join(Favorite, and_(Favorite.opportunity_id == Opportunity.id, Favorite.user_id == user.id))
        .outerjoin(Application, and_(Application.opportunity_id == Opportunity.id, Application.user_id == user.id))
        .where(Application.id.is_(None), Opportunity.deadline_at.between(start, end))
    ).all()
    events += [
        CalendarEvent(
            id=f"fav:{o.id}",
            kind="favorite_deadline",
            title=o.title,
            subtitle=o.organization,
            at=o.deadline_at,
            deadline_status=o.deadline_status,
            opportunity_id=str(o.id),
        )
        for o in favs
        if o.deadline_at
    ]
    tasks = db.scalars(
        select(Task).where(Task.user_id == user.id, Task.due_at.between(start, end), Task.status != "cancelled")
    ).all()
    events += [
        CalendarEvent(
            id=f"task:{t.id}",
            kind="task",
            title=t.title,
            at=t.due_at,
            status=t.status,
            application_id=str(t.application_id) if t.application_id else None,
            overdue=bool(t.due_at and t.due_at < now and t.status in ("todo", "in_progress")),
        )
        for t in tasks
        if t.due_at
    ]
    return sorted(events, key=lambda e: e.at)
