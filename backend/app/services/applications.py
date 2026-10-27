from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.core.text import normalize_text
from app.core.timeutil import utcnow
from app.models import (
    Application,
    ApplicationDocument,
    ApplicationEvent,
    Document,
    Match,
    Opportunity,
    Task,
    User,
)
from app.models.enums import ApplicationStatus, TaskStatus
from app.schemas.application import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    LinkedDocument,
    OpportunityBrief,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    UrgencyOut,
)
from app.services.priority import compute_urgency

SUBMITTED_STATES = {ApplicationStatus.SUBMITTED, ApplicationStatus.SELECTION, ApplicationStatus.ACCEPTED}

# Correspondance entre documents exigés (texte libre) et types de documents.
_DOC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cv": ("cv", "curriculum", "resume", "lebenslauf"),
    "cover_letter": ("motivation", "cover letter", "lettre de motivation", "motivational", "anschreiben"),
    "transcript": ("transcript", "releve", "notes", "grades", "academic records"),
    "diploma": ("diplome", "diploma", "degree certificate", "certificate of degree", "zeugnis"),
    "language_certificate": (
        "ielts",
        "toefl",
        "delf",
        "dalf",
        "tcf",
        "language certificate",
        "certificat de langue",
        "cambridge",
        "goethe",
        "testdaf",
    ),
    "recommendation_letter": ("recommendation", "recommandation", "reference letter", "referee"),
    "essay": ("essay", "statement", "personal statement", "research proposal", "essai"),
}


def required_doc_types(required: list[str]) -> set[str]:
    found: set[str] = set()
    for item in required:
        norm = normalize_text(item)
        for doc_type, words in _DOC_KEYWORDS.items():
            if any(w in norm for w in words):
                found.add(doc_type)
    return found


def _get_owned(db: Session, user: User, application_id: uuid.UUID) -> Application:
    app = db.scalar(select(Application).where(Application.id == application_id, Application.user_id == user.id))
    if app is None:
        raise NotFound("Candidature introuvable.")
    return app


def _event(db: Session, app: Application, event_type: str, **kwargs: Any) -> None:
    db.add(ApplicationEvent(application_id=app.id, user_id=app.user_id, event_type=event_type, **kwargs))


def _serialize(db: Session, user: User, apps: list[Application]) -> list[ApplicationOut]:
    if not apps:
        return []
    ids = [a.id for a in apps]
    opps = {
        o.id: o for o in db.scalars(select(Opportunity).where(Opportunity.id.in_({a.opportunity_id for a in apps})))
    }
    matches = {
        m.opportunity_id: m
        for m in db.scalars(select(Match).where(Match.user_id == user.id, Match.opportunity_id.in_(list(opps))))
    }
    docs: dict[uuid.UUID, list[LinkedDocument]] = defaultdict(list)
    for link, doc in db.execute(
        select(ApplicationDocument, Document)
        .join(Document, Document.id == ApplicationDocument.document_id)
        .where(ApplicationDocument.application_id.in_(ids))
        .order_by(ApplicationDocument.added_at)
    ).all():
        docs[link.application_id].append(
            LinkedDocument(
                id=doc.id,
                title=doc.title,
                doc_type=doc.doc_type,
                version=doc.version,
                role=link.role,
                added_at=link.added_at,
            )
        )
    open_tasks = dict(
        db.execute(
            select(Task.application_id, func.count())
            .where(Task.application_id.in_(ids), Task.status.in_((TaskStatus.TODO, TaskStatus.IN_PROGRESS)))
            .group_by(Task.application_id)
        ).all()
    )
    out: list[ApplicationOut] = []
    for app in apps:
        opp = opps[app.opportunity_id]
        match = matches.get(opp.id)
        linked_types = {d.doc_type for d in docs[app.id]}
        missing = len(required_doc_types(opp.required_documents) - linked_types)
        deadline = app.deadline_at or opp.deadline_at
        item = ApplicationOut.model_validate(
            {
                **{k: getattr(app, k) for k in ApplicationOut.model_fields if hasattr(app, k) and k != "opportunity"},
                "opportunity": OpportunityBrief.model_validate(opp),
            }
        )
        item.documents = docs[app.id]
        item.open_tasks = open_tasks.get(app.id, 0)
        item.eligibility = match.eligibility if match else None
        item.score = match.score if match else None
        if app.status not in (*SUBMITTED_STATES, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN):
            u = compute_urgency(
                deadline_at=deadline,
                deadline_status="confirmed" if app.deadline_at else opp.deadline_status,
                eligibility=item.eligibility,
                score=item.score,
                missing_documents=missing,
                estimated_prep_hours=app.estimated_prep_hours,
                next_action_at=app.next_action_at,
                tz=user.timezone,
            )
            item.urgency = UrgencyOut(level=u.level, score=u.score, reasons=u.reasons, days_left=u.days_left)
        out.append(item)
    return out


def list_applications(db: Session, user: User, status: str | None = None) -> list[ApplicationOut]:
    query = select(Application).where(Application.user_id == user.id)
    if status:
        query = query.where(Application.status == status)
    apps = list(db.scalars(query.order_by(Application.updated_at.desc())))
    return _serialize(db, user, apps)


def get_application(db: Session, user: User, application_id: uuid.UUID) -> ApplicationOut:
    return _serialize(db, user, [_get_owned(db, user, application_id)])[0]


def create_application(db: Session, user: User, data: ApplicationCreate) -> ApplicationOut:
    opp = db.get(Opportunity, data.opportunity_id)
    if opp is None:
        raise NotFound("Opportunité introuvable.")
    existing = db.scalar(
        select(Application.id).where(Application.user_id == user.id, Application.opportunity_id == opp.id)
    )
    if existing:
        raise Conflict(
            "Cette opportunité est déjà suivie.", code="application_exists", details={"application_id": str(existing)}
        )
    app = Application(
        user_id=user.id,
        opportunity_id=opp.id,
        status=data.status.value,
        notes=data.notes,
        deadline_at=opp.deadline_at if opp.deadline_status == "confirmed" else None,
    )
    db.add(app)
    try:
        db.flush()
    except IntegrityError as exc:  # course entre deux requêtes simultanées
        db.rollback()
        raise Conflict("Cette opportunité est déjà suivie.", code="application_exists") from exc
    _event(db, app, "created", to_status=app.status, details={"opportunity_title": opp.title})
    db.commit()
    return get_application(db, user, app.id)


_TRACKED_FIELDS = (
    "deadline_at",
    "submitted_at",
    "notes",
    "contact_name",
    "contact_email",
    "next_action",
    "next_action_at",
    "follow_up_at",
    "response_notes",
    "response_received_at",
    "estimated_prep_hours",
)


def update_application(db: Session, user: User, application_id: uuid.UUID, data: ApplicationUpdate) -> ApplicationOut:
    app = _get_owned(db, user, application_id)
    provided = data.model_dump(exclude_unset=True)
    changed: list[str] = []
    for key in _TRACKED_FIELDS:
        if key in provided and getattr(app, key) != provided[key]:
            setattr(app, key, provided[key])
            changed.append(key)

    if data.status is not None and data.status.value != app.status:
        target = data.status
        needs_submission = target in SUBMITTED_STATES and app.submission_confirmed_at is None
        if needs_submission and not data.confirm_submission:
            raise AppError(
                "Confirmez explicitement que vous avez vous-même envoyé la candidature.",
                code="submission_confirmation_required",
                status_code=422,
            )
        if needs_submission:
            app.submission_confirmed_at = utcnow()
            if app.submitted_at is None:
                app.submitted_at = utcnow()
                changed.append("submitted_at")
        previous = app.status
        app.status = target.value
        _event(db, app, "status_changed", from_status=previous, to_status=app.status)
    if changed:
        _event(db, app, "fields_updated", details={"fields": changed})
    db.flush()
    db.commit()
    return get_application(db, user, app.id)


def delete_application(db: Session, user: User, application_id: uuid.UUID) -> None:
    app = _get_owned(db, user, application_id)
    db.delete(app)
    db.commit()


def list_events(db: Session, user: User, application_id: uuid.UUID) -> list[ApplicationEvent]:
    _get_owned(db, user, application_id)
    return list(
        db.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.created_at.desc())
        )
    )


def link_document(
    db: Session, user: User, application_id: uuid.UUID, document_id: uuid.UUID, role: str | None
) -> ApplicationOut:
    app = _get_owned(db, user, application_id)
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if doc is None:
        raise NotFound("Document introuvable.")
    exists = db.get(ApplicationDocument, (app.id, doc.id))
    if exists is None:
        db.add(ApplicationDocument(application_id=app.id, document_id=doc.id, user_id=user.id, role=role))
        _event(db, app, "document_linked", details={"document_id": str(doc.id), "title": doc.title})
        db.commit()
    return get_application(db, user, app.id)


def unlink_document(db: Session, user: User, application_id: uuid.UUID, document_id: uuid.UUID) -> ApplicationOut:
    app = _get_owned(db, user, application_id)
    link = db.get(ApplicationDocument, (app.id, document_id))
    if link is not None:
        db.delete(link)
        _event(db, app, "document_unlinked", details={"document_id": str(document_id)})
        db.commit()
    return get_application(db, user, app.id)


# ------------------------------------------------------------------ tâches
def _task_out(task: Task, title: str | None = None) -> TaskOut:
    out = TaskOut.model_validate(task)
    out.overdue = bool(task.due_at and task.due_at < utcnow() and task.status in ("todo", "in_progress"))
    out.application_title = title
    return out


def create_task(db: Session, user: User, data: TaskCreate) -> TaskOut:
    title = None
    if data.application_id:
        app = _get_owned(db, user, data.application_id)
        opp = db.get(Opportunity, app.opportunity_id)
        title = opp.title if opp else None
    task = Task(user_id=user.id, **data.model_dump())
    db.add(task)
    db.flush()
    if data.application_id:
        _event(db, app, "task_created", details={"task_id": str(task.id), "title": task.title})
    db.commit()
    return _task_out(task, title)


def list_tasks(
    db: Session,
    user: User,
    *,
    status: str | None = None,
    application_id: uuid.UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    overdue: bool = False,
    include_done: bool = False,
) -> list[TaskOut]:
    query = (
        select(Task, Opportunity.title)
        .outerjoin(Application, and_(Application.id == Task.application_id, Application.user_id == user.id))
        .outerjoin(Opportunity, Opportunity.id == Application.opportunity_id)
        .where(Task.user_id == user.id)
    )
    if status:
        query = query.where(Task.status == status)
    elif not include_done:
        query = query.where(Task.status.in_(("todo", "in_progress")))
    if application_id:
        query = query.where(Task.application_id == application_id)
    if due_before:
        query = query.where(Task.due_at <= due_before)
    if due_after:
        query = query.where(Task.due_at >= due_after)
    if overdue:
        query = query.where(Task.due_at < utcnow(), Task.status.in_(("todo", "in_progress")))
    rows = db.execute(query.order_by(Task.due_at.asc().nulls_last(), Task.created_at)).all()
    return [_task_out(task, title) for task, title in rows]


def update_task(db: Session, user: User, task_id: uuid.UUID, data: TaskUpdate) -> TaskOut:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if task is None:
        raise NotFound("Tâche introuvable.")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(task, key, value.value if hasattr(value, "value") else value)
    if data.status is not None:
        task.completed_at = utcnow() if data.status == TaskStatus.DONE else None
    db.commit()
    title = None
    if task.application_id:
        title = db.scalar(
            select(Opportunity.title)
            .join(Application, Application.opportunity_id == Opportunity.id)
            .where(Application.id == task.application_id)
        )
    return _task_out(task, title)


def delete_task(db: Session, user: User, task_id: uuid.UUID) -> None:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user.id))
    if task is None:
        raise NotFound("Tâche introuvable.")
    db.delete(task)
    db.commit()
