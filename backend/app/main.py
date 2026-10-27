"""Point d'entrée FastAPI : uvicorn app.main:app --host 0.0.0.0 --port $PORT"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, log_event

logger = logging.getLogger("app.http")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    problems = settings.check_production_ready()
    if problems:
        raise RuntimeError("Configuration de production invalide : " + "; ".join(problems))

    app = FastAPI(
        title="Opportunity Intelligence API",
        version="1.0.0",
        description=(
            "API de recherche, de matching explicable et de suivi des candidatures (stages et bourses de master). "
            "Authentification : `Authorization: Bearer <jeton de session>` obtenu via `/api/v1/auth/login`. "
            "Aucune candidature n'est jamais envoyée automatiquement."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers.setdefault("Cache-Control", "no-store")
        if request.url.path != "/api/v1/health":
            log_event(
                logger,
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                request_id=request_id,
            )
        return response

    install_error_handlers(app)
    app.include_router(api_router)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "opportunity-intelligence-api", "health": "/api/v1/health"}

    return app


app = create_app()
