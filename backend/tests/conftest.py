"""Tests exécutés sur une VRAIE base PostgreSQL (TEST_DATABASE_URL), jamais sur la production.

Par défaut : postgresql://postgres:postgres@localhost:5432/oi_test
"""

from __future__ import annotations

import os
import tempfile

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/oi_test")
if "neon.tech" in TEST_DB or os.environ.get("APP_ENV") == "production":
    raise RuntimeError("Les tests refusent de s'exécuter sur une base de production.")

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DB,
        "SECRET_KEY": "test-secret-key-not-used-in-production-0123456789",
        "STORAGE_PROVIDER": "local",
        "STORAGE_LOCAL_DIR": tempfile.mkdtemp(prefix="oi-test-storage-"),
        "FRONTEND_URL": "http://localhost:3000",
        "RESEND_API_KEY": "",
        "EMAIL_FROM": "",
        "AI_PROVIDER": "",
        "AI_API_KEY": "",
        "ALERT_RECIPIENT": "",
        "EMAIL_ALLOWED_RECIPIENTS": "",
    }
)

from collections.abc import Iterator  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings, normalize_database_url  # noqa: E402
from app.db.session import get_engine, get_sessionmaker  # noqa: E402
from app.models import Base, User  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from app.workers.notifications.email import SimulationEmailClient, set_email_client  # noqa: E402

PASSWORD = "Mot-de-passe-solide-2026"


def _alembic_config() -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    cfg.attributes["database_url"] = normalize_database_url(TEST_DB)
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = _alembic_config()
    # Vérifie aussi que les migrations sont réversibles.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def outbox() -> Iterator[SimulationEmailClient]:
    client = SimulationEmailClient()
    set_email_client(client)
    yield client
    set_email_client(None)


@pytest.fixture
def db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c


def make_user(db: Session, email: str = "moi@example.com", *, admin: bool = False) -> User:
    return auth_service.create_user(db, email, PASSWORD, is_admin=admin)


def login(client: TestClient, email: str = "moi@example.com", password: str = PASSWORD) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture
def user(db: Session) -> User:
    return make_user(db, admin=True)


@pytest.fixture
def auth(client: TestClient, user: User) -> dict[str, str]:
    return login(client)


@pytest.fixture
def settings() -> Any:
    return get_settings()
