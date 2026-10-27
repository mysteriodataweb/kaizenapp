from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import ApplicationStatus, TaskStatus
from app.schemas.application import (
    ApplicationCreate,
    ApplicationEventOut,
    ApplicationOut,
    ApplicationUpdate,
    LinkDocumentIn,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services import applications as service

router = APIRouter(tags=["candidatures"])


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(
    user: CurrentUser, db: DbSession, status: ApplicationStatus | None = None
) -> list[ApplicationOut]:
    return service.list_applications(db, user, status.value if status else None)


@router.post("/applications", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def create_application(data: ApplicationCreate, user: CurrentUser, db: DbSession) -> ApplicationOut:
    return service.create_application(db, user, data)


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def get_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationOut:
    return service.get_application(db, user, application_id)


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationOut,
    summary="Met à jour une candidature (« envoyée » exige confirm_submission=true)",
)
def update_application(
    application_id: uuid.UUID, data: ApplicationUpdate, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    return service.update_application(db, user, application_id, data)


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.delete_application(db, user, application_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications/{application_id}/events", response_model=list[ApplicationEventOut])
def list_events(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[ApplicationEventOut]:
    return [ApplicationEventOut.model_validate(e) for e in service.list_events(db, user, application_id)]


@router.post("/applications/{application_id}/documents", response_model=ApplicationOut)
def link_document(application_id: uuid.UUID, data: LinkDocumentIn, user: CurrentUser, db: DbSession) -> ApplicationOut:
    return service.link_document(db, user, application_id, data.document_id, data.role)


@router.delete("/applications/{application_id}/documents/{document_id}", response_model=ApplicationOut)
def unlink_document(
    application_id: uuid.UUID, document_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    return service.unlink_document(db, user, application_id, document_id)


@router.post("/applications/{application_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_application_task(application_id: uuid.UUID, data: TaskCreate, user: CurrentUser, db: DbSession) -> TaskOut:
    data.application_id = application_id
    return service.create_task(db, user, data)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    user: CurrentUser,
    db: DbSession,
    status: TaskStatus | None = None,
    application_id: uuid.UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    overdue: bool = False,
    include_done: bool = False,
) -> list[TaskOut]:
    return service.list_tasks(
        db,
        user,
        status=status.value if status else None,
        application_id=application_id,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
        include_done=include_done,
    )


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, user: CurrentUser, db: DbSession) -> TaskOut:
    return service.create_task(db, user, data)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: uuid.UUID, data: TaskUpdate, user: CurrentUser, db: DbSession) -> TaskOut:
    return service.update_task(db, user, task_id, data)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.delete_task(db, user, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
