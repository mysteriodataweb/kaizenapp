from __future__ import annotations

import hashlib
import io
import re
import uuid
import zipfile
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.models import ApplicationDocument, Document, User
from app.schemas.misc import DocumentOut, DocumentUpdate
from app.services.storage import get_storage

ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}


def sniff_mime(data: bytes) -> str | None:
    """Type réel déterminé par la signature binaire (le type annoncé par le client n'est pas fiable)."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if "[Content_Types].xml" in names and any(n.startswith("word/") for n in names):
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            return None
        return None
    try:
        sample = data[:4096].decode("utf-8")
        if "\x00" not in sample:
            return "text/plain"
    except UnicodeDecodeError:
        return None
    return None


def safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ]", "_", name, flags=re.UNICODE).strip(" .") or "document"
    return name[:200]


def validate_upload(data: bytes, declared_mime: str | None) -> str:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if not data:
        raise AppError("Fichier vide.", code="empty_file", status_code=422)
    if len(data) > max_bytes:
        raise AppError(
            f"Fichier trop volumineux (max {get_settings().max_upload_mb} Mo).", code="file_too_large", status_code=413
        )
    mime = sniff_mime(data)
    if mime is None or mime not in ALLOWED_MIME:
        raise AppError(
            "Type de fichier non autorisé (PDF, DOCX, PNG, JPEG ou texte).", code="unsupported_type", status_code=415
        )
    if (
        declared_mime
        and declared_mime not in (mime, "application/octet-stream")
        and not (mime == "text/plain" and declared_mime.startswith("text/"))
    ):
        raise AppError("Le contenu ne correspond pas au type annoncé.", code="mime_mismatch", status_code=415)
    return mime


def _out(db: Session, docs: list[Document]) -> list[DocumentOut]:
    links: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if docs:
        for app_id, doc_id in db.execute(
            select(ApplicationDocument.application_id, ApplicationDocument.document_id).where(
                ApplicationDocument.document_id.in_([d.id for d in docs])
            )
        ).all():
            links[doc_id].append(app_id)
    result = []
    for d in docs:
        out = DocumentOut.model_validate(d)
        out.application_ids = links[d.id]
        result.append(out)
    return result


def list_documents(db: Session, user: User, doc_type: str | None = None) -> list[DocumentOut]:
    query = select(Document).where(Document.user_id == user.id)
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    return _out(db, list(db.scalars(query.order_by(Document.created_at.desc()))))


def get_owned(db: Session, user: User, document_id: uuid.UUID) -> Document:
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if doc is None:
        raise NotFound("Document introuvable.")
    return doc


def upload(
    db: Session,
    user: User,
    *,
    data: bytes,
    filename: str,
    declared_mime: str | None,
    doc_type: str,
    title: str | None,
    notes: str | None,
    replaces: uuid.UUID | None = None,
) -> DocumentOut:
    mime = validate_upload(data, declared_mime)
    group_id, version = uuid.uuid4(), 1
    if replaces:
        previous = get_owned(db, user, replaces)
        group_id = previous.group_id
        version = (
            db.scalar(
                select(func.max(Document.version)).where(Document.user_id == user.id, Document.group_id == group_id)
            )
            or 0
        ) + 1
    doc_id = uuid.uuid4()
    key = f"users/{user.id}/{doc_id}{ALLOWED_MIME[mime]}"
    storage = get_storage()
    storage.put(key, data, mime)
    doc = Document(
        id=doc_id,
        user_id=user.id,
        group_id=group_id,
        version=version,
        doc_type=doc_type,
        title=(title or safe_filename(filename)).strip()[:200],
        original_filename=safe_filename(filename),
        mime_type=mime,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
        notes=notes,
    )
    db.add(doc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)  # pas de fichier orphelin
        raise
    return _out(db, [doc])[0]


def update(db: Session, user: User, document_id: uuid.UUID, data: DocumentUpdate) -> DocumentOut:
    doc = get_owned(db, user, document_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(doc, key, value.value if hasattr(value, "value") else value)
    db.commit()
    return _out(db, [doc])[0]


def delete(db: Session, user: User, document_id: uuid.UUID) -> None:
    doc = get_owned(db, user, document_id)
    key = doc.storage_key
    db.delete(doc)
    db.commit()
    get_storage().delete(key)
