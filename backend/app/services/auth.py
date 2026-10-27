"""Authentification locale : Argon2id + sessions opaques côté serveur.

Pas d'inscription publique : le compte administrateur est créé par la CLI
(`python -m app.cli create-admin`) ou par l'amorçage unique `bootstrap-admin`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, TooManyRequests, Unauthorized
from app.core.logging import log_event
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    password_problems,
    verify_password,
)
from app.core.timeutil import utcnow
from app.models import AuthAttempt, AuthSession, PasswordResetToken, User
from app.models.notification import NotificationPreference

logger = logging.getLogger("app.auth")

MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 20
FAILURE_WINDOW = timedelta(minutes=15)
VISIT_GAP = timedelta(minutes=30)
TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass
class LoginResult:
    token: str
    session: AuthSession
    user: User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def _recent_failures(db: Session, key: str) -> int:
    since = utcnow() - FAILURE_WINDOW
    return (
        db.scalar(
            select(func.count())
            .select_from(AuthAttempt)
            .where(AuthAttempt.key == key, AuthAttempt.success.is_(False), AuthAttempt.attempted_at >= since)
        )
        or 0
    )


def _record_attempt(db: Session, key: str, success: bool) -> None:
    db.add(AuthAttempt(key=key, success=success))


def login(db: Session, email: str, password: str, ip_key: str, user_agent: str | None) -> LoginResult:
    email_key = "email:" + hash_token(email.strip().lower())
    if _recent_failures(db, email_key) >= MAX_FAILURES_PER_EMAIL or _recent_failures(db, ip_key) >= MAX_FAILURES_PER_IP:
        log_event(logger, "login rate limited", logging.WARNING)
        raise TooManyRequests("Trop de tentatives. Réessayez dans 15 minutes.")

    user = get_user_by_email(db, email)
    ok = verify_password(user.password_hash if user else None, password)
    if not user or not ok or not user.is_active:
        _record_attempt(db, email_key, False)
        _record_attempt(db, ip_key, False)
        db.commit()
        raise Unauthorized("Identifiants invalides.", code="invalid_credentials")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    _record_attempt(db, email_key, True)
    now = utcnow()
    user.last_login_at = now
    token = new_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + timedelta(hours=get_settings().session_ttl_hours),
        last_used_at=now,
        user_agent=(user_agent or "")[:300] or None,
    )
    db.add(session)
    _touch_visit(user, now, force=True)
    db.commit()
    log_event(logger, "login success", user_id=str(user.id))
    return LoginResult(token=token, session=session, user=user)


def _touch_visit(user: User, now, force: bool = False) -> bool:  # type: ignore[no-untyped-def]
    last = user.last_seen_at
    if last is None or now - last > VISIT_GAP:
        user.previous_seen_at = last
        user.last_seen_at = now
        return True
    if force or now - last > TOUCH_INTERVAL:
        user.last_seen_at = now
        return True
    return False


def resolve_token(db: Session, token: str) -> tuple[User, AuthSession]:
    if not token or len(token) > 200:
        raise Unauthorized("Session invalide.")
    now = utcnow()
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        raise Unauthorized("Session invalide.")
    session, user = row
    if session.revoked_at is not None or session.expires_at <= now or not user.is_active:
        raise Unauthorized("Session expirée.")
    changed = _touch_visit(user, now)
    if session.last_used_at is None or now - session.last_used_at > TOUCH_INTERVAL:
        session.last_used_at = now
        changed = True
    if changed:
        db.commit()
    return user, session


def logout(db: Session, session: AuthSession) -> None:
    session.revoked_at = utcnow()
    db.commit()


def revoke_all_sessions(db: Session, user_id, except_session_id=None) -> int:  # type: ignore[no-untyped-def]
    stmt = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_session_id is not None:
        stmt = stmt.where(AuthSession.id != except_session_id)
    result = db.execute(stmt.values(revoked_at=utcnow()))
    return result.rowcount or 0


def _validate_new_password(password: str, email: str) -> None:
    problems = password_problems(password, email)
    if problems:
        raise AppError("Mot de passe trop faible.", code="weak_password", details=problems, status_code=422)


def change_password(db: Session, user: User, session: AuthSession, current: str, new: str) -> None:
    if not verify_password(user.password_hash, current):
        raise AppError("Mot de passe actuel incorrect.", code="invalid_password", status_code=400)
    _validate_new_password(new, user.email)
    user.password_hash = hash_password(new)
    user.password_changed_at = utcnow()
    revoke_all_sessions(db, user.id, except_session_id=session.id)
    db.commit()


def create_password_reset(db: Session, email: str) -> tuple[User, str] | None:
    """Crée un jeton de réinitialisation. Retourne None si le compte n'existe pas
    (la réponse HTTP reste identique pour ne pas révéler l'existence du compte)."""
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        return None
    recent = db.scalar(
        select(func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at >= utcnow() - timedelta(hours=1),
        )
    )
    if (recent or 0) >= 3:
        return None
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=get_settings().password_reset_ttl_minutes),
        )
    )
    db.commit()
    return user, token


def confirm_password_reset(db: Session, token: str, new_password: str) -> User:
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise AppError("Lien de réinitialisation invalide ou expiré.", code="invalid_reset_token")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise AppError("Lien de réinitialisation invalide ou expiré.", code="invalid_reset_token")
    _validate_new_password(new_password, user.email)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    row.used_at = utcnow()
    revoke_all_sessions(db, user.id)
    db.commit()
    return user


def create_user(
    db: Session, email: str, password: str, *, is_admin: bool = False, display_name: str | None = None
) -> User:
    email = email.strip()
    if get_user_by_email(db, email):
        raise AppError("Un compte existe déjà pour cette adresse.", code="user_exists", status_code=409)
    _validate_new_password(password, email)
    settings = get_settings()
    user = User(
        email=email,
        password_hash=hash_password(password),
        is_admin=is_admin,
        display_name=display_name,
        timezone=settings.default_timezone,
        password_changed_at=utcnow(),
    )
    db.add(user)
    db.flush()
    db.add(NotificationPreference(user_id=user.id, email=email))
    db.commit()
    return user


def cleanup_auth_tables(db: Session) -> dict[str, int]:
    now = utcnow()
    a = db.execute(delete(AuthAttempt).where(AuthAttempt.attempted_at < now - timedelta(days=7))).rowcount
    s = db.execute(
        delete(AuthSession).where(
            (AuthSession.expires_at < now - timedelta(days=7)) | (AuthSession.revoked_at < now - timedelta(days=7))
        )
    ).rowcount
    r = db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at < now - timedelta(days=1))).rowcount
    db.commit()
    return {"auth_attempts": a or 0, "sessions": s or 0, "reset_tokens": r or 0}
