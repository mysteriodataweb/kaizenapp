"""Inscription publique : fermée par défaut, adresse confirmée obligatoire, réponses non divulgatrices,
destinataires d'alertes limités, modération par l'administrateur, suppression de compte."""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.timeutil import utcnow
from app.models import Application, AuthSession, Document, EmailVerificationToken, NotificationPreference, Profile, User
from app.workers.notifications import service as notif
from tests.conftest import PASSWORD, login, make_user

NEW_EMAIL = "nouvelle@example.com"


@pytest.fixture
def open_registration(settings, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", True)
    return settings


def _register(client, email=NEW_EMAIL, password=PASSWORD, **extra):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, **extra})


def _token(outbox, index=-1):
    return re.search(r"token=([\w-]+)", outbox.outbox[index].text).group(1)


def test_registration_requires_email_confirmation(client, db, outbox, open_registration):
    assert client.get("/api/v1/auth/config").json() == {"registration_open": True}
    resp = _register(client, display_name="Awa")
    assert resp.status_code == 202, resp.text
    user = db.scalar(select(User).where(User.email == NEW_EMAIL))
    assert user is not None and not user.is_admin and user.email_verified_at is None
    assert user.display_name == "Awa"
    assert len(outbox.outbox) == 1
    mail = outbox.outbox[0]
    assert mail.to == NEW_EMAIL and "verify-email?token=" in mail.text

    # Connexion refusée tant que l'adresse n'est pas confirmée (mot de passe correct)
    blocked = client.post("/api/v1/auth/login", json={"email": NEW_EMAIL, "password": PASSWORD})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "email_not_verified"

    ok = client.post("/api/v1/auth/verify-email", json={"token": _token(outbox)})
    assert ok.status_code == 200, ok.text
    headers = login(client, NEW_EMAIL)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["email"] == NEW_EMAIL and me["is_admin"] is False
    # Lien à usage unique
    again = client.post("/api/v1/auth/verify-email", json={"token": _token(outbox)})
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_verification_token"


def test_wrong_password_on_unverified_account_stays_generic(client, outbox, open_registration):
    _register(client)
    resp = client.post("/api/v1/auth/login", json={"email": NEW_EMAIL, "password": "mauvais"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


def test_registration_response_does_not_reveal_existing_accounts(client, db, user, outbox, open_registration):
    fresh = _register(client)
    taken = _register(client, email="moi@example.com", password="Un-autre-mot-de-passe-2026")
    assert taken.status_code == fresh.status_code == 202
    assert taken.json() == fresh.json()
    # Le titulaire du compte existant est prévenu ; son mot de passe ne change pas
    assert outbox.outbox[-1].to == "moi@example.com"
    assert "verify-email" not in outbox.outbox[-1].text
    login(client)
    assert db.scalar(select(func.count()).select_from(User)) == 2


def test_registering_again_resends_confirmation_without_changing_password(client, db, outbox, open_registration):
    _register(client)
    _register(client, password="Mot-de-passe-pirate-2026")
    assert len(outbox.outbox) == 2
    client.post("/api/v1/auth/verify-email", json={"token": _token(outbox)})
    login(client, NEW_EMAIL, PASSWORD)
    bad = client.post("/api/v1/auth/login", json={"email": NEW_EMAIL, "password": "Mot-de-passe-pirate-2026"})
    assert bad.status_code == 401


def test_registration_validates_password(client, db, outbox, open_registration):
    resp = _register(client, password="court")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "weak_password"
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert outbox.outbox == []


def test_registration_rate_limited_per_ip(client, outbox, open_registration):
    for i in range(open_registration.registration_max_per_ip_per_hour):
        assert _register(client, email=f"user{i}@example.com").status_code == 202
    resp = _register(client, email="encore@example.com")
    assert resp.status_code == 429


def test_registration_global_cap(client, open_registration, monkeypatch):
    monkeypatch.setattr(open_registration, "registration_max_per_hour", 2)
    for i in range(2):
        headers = {"X-OI-Client-IP": f"10.0.0.{i}"}
        payload = {"email": f"user{i}@example.com", "password": PASSWORD}
        assert client.post("/api/v1/auth/register", json=payload, headers=headers).status_code == 202
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": PASSWORD},
        headers={"X-OI-Client-IP": "10.0.0.9"},
    )
    assert resp.status_code == 429


def test_registration_closed_in_production_without_email_provider(settings, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", True)
    monkeypatch.setattr(settings, "app_env", "production")
    assert settings.registration_open is False
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(settings, "email_from", "OI <alertes@example.com>")
    assert settings.registration_open is True


def test_expired_verification_link_and_resend(client, db, outbox, open_registration):
    _register(client)
    db.execute(EmailVerificationToken.__table__.update().values(expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()
    expired = client.post("/api/v1/auth/verify-email", json={"token": _token(outbox)})
    assert expired.status_code == 400

    unknown = client.post("/api/v1/auth/verify-email/resend", json={"email": "personne@example.com"})
    resent = client.post("/api/v1/auth/verify-email/resend", json={"email": NEW_EMAIL})
    assert unknown.status_code == resent.status_code == 202
    assert unknown.json() == resent.json()
    assert len(outbox.outbox) == 2
    assert client.post("/api/v1/auth/verify-email", json={"token": _token(outbox)}).status_code == 200
    # Plus rien à renvoyer une fois confirmé
    client.post("/api/v1/auth/verify-email/resend", json={"email": NEW_EMAIL})
    assert len(outbox.outbox) == 2


def test_verification_emails_are_capped(client, outbox, open_registration):
    _register(client)
    for _ in range(5):
        client.post("/api/v1/auth/verify-email/resend", json={"email": NEW_EMAIL})
    assert len(outbox.outbox) == 3


def test_password_reset_confirms_email(client, db, outbox, open_registration):
    _register(client)
    client.post("/api/v1/auth/password-reset/request", json={"email": NEW_EMAIL})
    token = _token(outbox)
    new_password = "Nouveau-mot-de-passe-2026"
    resp = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": new_password})
    assert resp.status_code == 200
    login(client, NEW_EMAIL, new_password)


def test_alerts_only_to_verified_own_address(db, settings, monkeypatch):
    monkeypatch.setattr(settings, "email_allowed_recipients", "equipe@example.com")
    admin = make_user(db, "admin@example.com", admin=True)
    member = make_user(db, "membre@example.com")
    assert notif.recipient_allowed("membre@example.com", member)
    # Les adresses supplémentaires de la configuration sont réservées à l'administrateur
    assert notif.recipient_allowed("equipe@example.com", admin)
    assert not notif.recipient_allowed("equipe@example.com", member)
    member.email_verified_at = None
    db.commit()
    assert not notif.recipient_allowed("membre@example.com", member)
    prefs = db.scalar(select(NotificationPreference).where(NotificationPreference.user_id == member.id))
    assert notif.effective_recipient(prefs, member) is None


def test_member_cannot_redirect_alerts_to_allowlisted_address(client, db, settings, monkeypatch):
    monkeypatch.setattr(settings, "email_allowed_recipients", "equipe@example.com")
    make_user(db, "membre@example.com")
    headers = login(client, "membre@example.com")
    prefs = client.get("/api/v1/notifications/preferences", headers=headers).json()
    prefs["email"] = "equipe@example.com"
    resp = client.put("/api/v1/notifications/preferences", headers=headers, json=prefs)
    assert resp.status_code == 422
    assert "ALERT_RECIPIENT" not in resp.json()["error"]["message"]


def test_admin_lists_and_disables_users(client, db, outbox, open_registration):
    make_user(db, "admin@example.com", admin=True)
    member = make_user(db, "membre@example.com")
    admin_headers = login(client, "admin@example.com")
    member_headers = login(client, "membre@example.com")
    assert client.get("/api/v1/admin/users", headers=member_headers).status_code == 403

    users = client.get("/api/v1/admin/users", headers=admin_headers).json()
    assert {u["email"] for u in users} == {"admin@example.com", "membre@example.com"}
    assert all("password_hash" not in u for u in users)

    resp = client.patch(f"/api/v1/admin/users/{member.id}", headers=admin_headers, json={"is_active": False})
    assert resp.status_code == 200 and resp.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", headers=member_headers).status_code == 401
    relogin = client.post("/api/v1/auth/login", json={"email": "membre@example.com", "password": PASSWORD})
    assert relogin.status_code == 401
    admin_id = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    self_off = client.patch(f"/api/v1/admin/users/{admin_id}", headers=admin_headers, json={"is_active": False})
    assert self_off.status_code == 409


def test_member_dashboard_hides_collection_errors(client, db):
    make_user(db, "membre@example.com")
    headers = login(client, "membre@example.com")
    resp = client.get("/api/v1/dashboard", headers=headers)
    assert resp.status_code == 200
    assert all(e["type"] != "collecte" for e in resp.json()["recent_errors"])


def test_delete_account_removes_all_data(client, db, settings):
    make_user(db, "admin@example.com", admin=True)
    member = make_user(db, "membre@example.com")
    member_id = member.id
    headers = login(client, "membre@example.com")
    client.put("/api/v1/profile", headers=headers, json={"full_name": "À supprimer", "languages": []})
    upload = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("cv.pdf", b"%PDF-1.4\n%test\n", "application/pdf")},
        data={"doc_type": "cv", "title": "CV"},
    )
    assert upload.status_code == 201, upload.text
    stored = Path(settings.storage_local_dir) / db.scalar(select(Document.storage_key))
    assert stored.exists()

    wrong = client.post("/api/v1/auth/delete-account", headers=headers, json={"password": "mauvais"})
    assert wrong.status_code == 400
    resp = client.post("/api/v1/auth/delete-account", headers=headers, json={"password": PASSWORD})
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.get(User, member_id) is None
    for model in (Profile, Document, Application, AuthSession, NotificationPreference):
        assert db.scalar(select(func.count()).select_from(model).where(model.user_id == member_id)) == 0
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert not stored.exists()


def test_last_admin_cannot_delete_account(client, db):
    make_user(db, "admin@example.com", admin=True)
    headers = login(client, "admin@example.com")
    resp = client.post("/api/v1/auth/delete-account", headers=headers, json={"password": PASSWORD})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "last_admin"
