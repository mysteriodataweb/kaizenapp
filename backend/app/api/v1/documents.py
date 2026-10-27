from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.models.enums import DocumentType
from app.schemas.misc import DocumentOut, DocumentUpdate, DownloadLink
from app.services import documents as service
from app.services.storage import SIGNED_URL_TTL, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(user: CurrentUser, db: DbSession, doc_type: DocumentType | None = None) -> list[DocumentOut]:
    return service.list_documents(db, user, doc_type.value if doc_type else None)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED, summary="Téléverse un document privé")
def upload_document(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    doc_type: DocumentType = Form(...),
    title: str | None = Form(default=None, max_length=200),
    notes: str | None = Form(default=None, max_length=5000),
    replaces: uuid.UUID | None = Form(default=None, description="Nouvelle version d'un document existant"),
) -> DocumentOut:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError(
            f"Fichier trop volumineux (max {get_settings().max_upload_mb} Mo).", code="file_too_large", status_code=413
        )
    return service.upload(
        db,
        user,
        data=data,
        filename=file.filename or "document",
        declared_mime=file.content_type,
        doc_type=doc_type.value,
        title=title,
        notes=notes,
        replaces=replaces,
    )


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(document_id: uuid.UUID, data: DocumentUpdate, user: CurrentUser, db: DbSession) -> DocumentOut:
    return service.update(db, user, document_id, data)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    service.delete(db, user, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{document_id}/download", response_model=DownloadLink, summary="Lien de téléchargement à durée limitée")
def download_link(document_id: uuid.UUID, user: CurrentUser, db: DbSession) -> DownloadLink:
    doc = service.get_owned(db, user, document_id)
    url = get_storage().signed_url(doc.storage_key, doc.original_filename)
    if url:
        return DownloadLink(mode="redirect", url=url, expires_in=SIGNED_URL_TTL)
    return DownloadLink(mode="proxy", url=f"/documents/{doc.id}/content", expires_in=0)


@router.get("/{document_id}/content", summary="Contenu du document (accès authentifié)")
def document_content(document_id: uuid.UUID, user: CurrentUser, db: DbSession) -> StreamingResponse:
    doc = service.get_owned(db, user, document_id)
    safe = doc.original_filename.replace('"', "")
    return StreamingResponse(
        get_storage().open(doc.storage_key),
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
