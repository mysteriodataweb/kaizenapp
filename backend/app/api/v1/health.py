from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import get_settings
from app.services.storage import get_storage

router = APIRouter(tags=["santé"])


@router.get("/health", summary="État du service et de la base de données")
def health(db: DbSession) -> JSONResponse:
    settings = get_settings()
    db_ok, revision = True, None
    try:
        db.execute(text("SELECT 1"))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "environment": settings.app_env,
        "database": "ok" if db_ok else "unreachable",
        "migration": revision,
        "email_mode": "resend" if settings.email_enabled else "simulation",
        "ai_enabled": settings.ai_enabled,
        "storage": get_storage().name,
    }
    return JSONResponse(status_code=200 if db_ok else 503, content=body)
