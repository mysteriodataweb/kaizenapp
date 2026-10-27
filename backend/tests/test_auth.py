from __future__ import annotations

import re

from sqlalchemy import select

from app.models import AuthSession, User
from tests.conftest import PASSWORD, login, make_user


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] == "ok"
    assert body["email_mode"] == "simulation"
    assert body["ai_enabled"] is False


def test_login_success_and_me(client, user):
    headers = login(client)
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "moi@example.com"
    assert "password_hash" not in me.json()


def test_login_wrong_password(client, user):
    resp = client.post("/api/v1/auth/login", json={"email": "moi@example.com", "password": "mauvais"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_user_same_error(client, user):
    resp = client.post("/api/v1/auth/login", json={"email": "inconnu@example.com", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_login_rate_limited_after_failures(client, user):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "moi@example.com", "password": "mauvais"})
    resp = client.post("/api/v1/auth/login", json={"email": "moi@example.com", "password": PASSWORD})
    assert resp.status_code == 429


def test_no_public_registration(client):
    assert client.post("/api/v1/auth/register", json={"email": "a@b.co", "password": PASSWORD}).status_code in (
        404,
        405,
    )


def test_private_routes_require_auth(client):
    for path in (
        "/api/v1/profile",
        "/api/v1/opportunities",
        "/api/v1/applications",
        "/api/v1/documents",
        "/api/v1/dashboard",
        "/api/v1/tasks",
        "/api/v1/notifications/preferences",
        "/api/v1/admin/sources",
    ):
        assert client.get(path).status_code == 401, path
    assert client.get("/api/v1/profile", headers={"Authorization": "Bearer faux-jeton"}).status_code == 401


def test_logout_revokes_session(client, user):
    headers = login(client)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_tokens_are_stored_hashed(client, user, db):
    headers = login(client)
    token = headers["Authorization"].split()[1]
    hashes = db.scalars(select(AuthSession.token_hash)).all()
    assert token not in hashes
    assert all(len(h) == 64 for h in hashes)


def test_password_is_hashed_with_argon2(db, user):
    stored = db.scalar(select(User.password_hash))
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_weak_password_rejected(db):
    import pytest

    from app.core.errors import AppError
    from app.services.auth import create_user

    with pytest.raises(AppError) as exc:
        create_user(db, "faible@example.com", "court")
    assert exc.value.code == "weak_password"


def test_password_reset_flow(client, user, outbox):
    old = login(client)
    resp = client.post("/api/v1/auth/password-reset/request", json={"email": "moi@example.com"})
    assert resp.status_code == 202
    # Réponse identique pour un compte inexistant
    other = client.post("/api/v1/auth/password-reset/request", json={"email": "personne@example.com"})
    assert other.json() == resp.json()
    assert len(outbox.outbox) == 1
    token = re.search(r"token=([\w-]+)", outbox.outbox[0].text).group(1)
    new_password = "Nouveau-mot-de-passe-2026"
    ok = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": new_password})
    assert ok.status_code == 200, ok.text
    # Jeton à usage unique et anciennes sessions révoquées
    again = client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": new_password + "x"}
    )
    assert again.status_code == 400
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    login(client, password=new_password)


def test_change_password_revokes_other_sessions(client, user):
    first = login(client)
    second = login(client)
    resp = client.post(
        "/api/v1/auth/change-password",
        headers=second,
        json={"current_password": PASSWORD, "new_password": "Encore-un-autre-mdp-2026"},
    )
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 200


def test_update_account_timezone_validation(client, auth):
    assert client.patch("/api/v1/auth/me", headers=auth, json={"timezone": "Mars/Olympus"}).status_code == 422
    resp = client.patch("/api/v1/auth/me", headers=auth, json={"timezone": "Africa/Dakar"})
    assert resp.json()["timezone"] == "Africa/Dakar"


def test_admin_routes_forbidden_for_non_admin(client, db):
    make_user(db, "simple@example.com", admin=False)
    headers = login(client, "simple@example.com")
    assert client.get("/api/v1/admin/sources", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/collect", headers=headers).status_code == 403


def test_oversized_request_rejected_early(client, auth, settings):
    resp = client.post(
        "/api/v1/documents",
        headers={
            **auth,
            "content-length": str((settings.max_upload_mb + 5) * 1024 * 1024),
            "content-type": "multipart/form-data; boundary=x",
        },
        content=b"--x--",
    )
    assert resp.status_code == 413


def test_security_headers(client):
    resp = client.get("/api/v1/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-request-id"]
    assert resp.headers["cache-control"] == "no-store"
