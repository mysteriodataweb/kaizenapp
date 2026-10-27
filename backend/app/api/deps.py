from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, Unauthorized
from app.core.security import keyed_hash
from app.db.session import get_db
from app.models import AuthSession, User
from app.services import auth as auth_service

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    session: AuthSession


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthorized("Authentification requise.")
    return token.strip()


def get_auth(request: Request, db: DbSession) -> AuthContext:
    """L'identité provient exclusivement du jeton de session vérifié côté serveur,
    jamais d'un user_id fourni par le client."""
    user, session = auth_service.resolve_token(db, _bearer(request))
    return AuthContext(user=user, session=session)


def get_current_user(ctx: Annotated[AuthContext, Depends(get_auth)]) -> User:
    return ctx.user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise Forbidden("Accès réservé à l'administrateur.")
    return user


def client_ip_key(request: Request) -> str:
    ip = (
        request.headers.get("x-oi-client-ip")
        or (request.headers.get("x-forwarded-for", "").split(",")[-1].strip())
        or (request.client.host if request.client else "unknown")
    )
    return "ip:" + keyed_hash(get_settings().secret_key, ip[:64])


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
Auth = Annotated[AuthContext, Depends(get_auth)]
