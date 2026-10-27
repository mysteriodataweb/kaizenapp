from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, UploadFile

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import session_scope
from app.models import User
from app.schemas.profile import CvExtractionOut, ProfileIn, ProfileOut
from app.services import cv_extract, matching
from app.services import profile as profile_service
from app.services.documents import sniff_mime

router = APIRouter(prefix="/profile", tags=["profil"])


def _recompute(user_id) -> None:  # type: ignore[no-untyped-def]
    with session_scope() as db:
        user = db.get(User, user_id)
        if user:
            matching.recompute_for_user(db, user)


@router.get("", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = profile_service.get_or_create(db, user)
    db.commit()
    return profile_service.to_out(profile)


@router.put("", response_model=ProfileOut, summary="Met à jour le profil et recalcule les scores")
def put_profile(data: ProfileIn, user: CurrentUser, db: DbSession, background: BackgroundTasks) -> ProfileOut:
    profile = profile_service.update(db, user, data)
    db.commit()
    background.add_task(_recompute, user.id)
    return profile_service.to_out(profile)


@router.post(
    "/cv-extract", response_model=CvExtractionOut, summary="Extrait des suggestions d'un CV PDF (sans enregistrer)"
)
def cv_extract_endpoint(user: CurrentUser, file: UploadFile = File(...)) -> CvExtractionOut:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AppError("Fichier trop volumineux.", code="file_too_large", status_code=413)
    if sniff_mime(data) != "application/pdf":
        raise AppError("Un fichier PDF est attendu.", code="unsupported_type", status_code=415)
    text, pages = cv_extract.extract_text(data)
    suggestions, evidence, warnings = cv_extract.extract_suggestions(text)
    return CvExtractionOut(
        text_length=len(text), pages=pages, suggestions=suggestions, evidence=evidence, warnings=warnings
    )
