"""Moteur SQLAlchemy et sessions. Compatible avec les connexions poolées Neon (PgBouncer)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        # Neon suspend le calcul après inactivité : on recycle les connexions.
        pool_recycle=300,
        # Désactive les requêtes préparées côté serveur (compatibilité PgBouncer transaction mode).
        connect_args={"prepare_threshold": None, "connect_timeout": 15},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """Session par requête. Les routes valident explicitement (commit) avant de répondre,
    afin qu'un échec d'écriture ne soit jamais masqué derrière une réponse 200."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = get_sessionmaker()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
