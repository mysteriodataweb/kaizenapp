from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, status

from app.api.deps import Auth, CurrentUser, DbSession, client_ip_key
from app.core.config import get_settings
from app.db.session import session_scope
from app.models import User
from app.schemas.auth import (
    AccountUpdateIn,
    ChangePasswordIn,
    LoginIn,
    LoginOut,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    UserOut,
)
from app.schemas.common import Message
from app.services import auth as auth_service
from app.workers.notifications.service import dispatch
from app.workers.notifications.templates import render_simple

router = APIRouter(prefix="/auth", tags=["authentification"])


@router.post("/login", response_model=LoginOut, summary="Connexion (aucune inscription publique)")
def login(data: LoginIn, request: Request, db: DbSession) -> LoginOut:
    result = auth_service.login(
        db, data.email, data.password, client_ip_key(request), request.headers.get("user-agent")
    )
    return LoginOut(token=result.token, expires_at=result.session.expires_at, user=UserOut.model_validate(result.user))


@router.post("/logout", response_model=Message)
def logout(ctx: Auth, db: DbSession) -> Message:
    auth_service.logout(db, ctx.session)
    return Message(message="Déconnecté.")


@router.post("/logout-all", response_model=Message, summary="Révoque toutes les autres sessions")
def logout_all(ctx: Auth, db: DbSession) -> Message:
    count = auth_service.revoke_all_sessions(db, ctx.user.id, except_session_id=ctx.session.id)
    db.commit()
    return Message(message=f"{count} autre(s) session(s) révoquée(s).")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(data: AccountUpdateIn, user: CurrentUser, db: DbSession) -> UserOut:
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=Message)
def change_password(data: ChangePasswordIn, ctx: Auth, db: DbSession) -> Message:
    auth_service.change_password(db, ctx.user, ctx.session, data.current_password, data.new_password)
    return Message(message="Mot de passe modifié. Les autres sessions ont été déconnectées.")


def _send_reset_email(user_id, token: str) -> None:  # type: ignore[no-untyped-def]
    with session_scope() as db:
        user = db.get(User, user_id)
        if user is None:
            return
        link = f"{get_settings().frontend_url.rstrip('/')}/reset-password?token={token}"
        html, text = render_simple(
            "Réinitialisation du mot de passe",
            [
                "Une réinitialisation de mot de passe a été demandée pour votre compte.",
                "Ce lien est valable 30 minutes et ne peut servir qu'une fois. "
                "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
            ],
            ("Choisir un nouveau mot de passe", link),
        )
        dispatch(
            db,
            user,
            kind="password_reset",
            dedup_key=f"reset:{token[:16]}",
            subject="[OI] Réinitialisation du mot de passe",
            html=html,
            text=text,
            recipient=user.email,
        )


@router.post("/password-reset/request", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
def password_reset_request(data: PasswordResetRequestIn, db: DbSession, background: BackgroundTasks) -> Message:
    created = auth_service.create_password_reset(db, data.email)
    if created is not None:
        user, token = created
        background.add_task(_send_reset_email, user.id, token)
    # Réponse identique que le compte existe ou non.
    return Message(message="Si un compte correspond, un e-mail de réinitialisation a été envoyé.")


@router.post("/password-reset/confirm", response_model=Message)
def password_reset_confirm(data: PasswordResetConfirmIn, db: DbSession) -> Message:
    auth_service.confirm_password_reset(db, data.token, data.new_password)
    return Message(message="Mot de passe réinitialisé. Vous pouvez vous connecter.")
