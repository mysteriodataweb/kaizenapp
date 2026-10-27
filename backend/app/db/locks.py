"""Verrou distribué à bail stocké en base (fonctionne derrière un pooler en mode transaction)."""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import JobLock


class LockNotAcquired(Exception):
    pass


def _holder() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:100]


def try_acquire(db: Session, name: str, ttl: timedelta) -> str | None:
    holder = _holder()
    now = utcnow()
    row = db.execute(
        text(
            """
            INSERT INTO job_locks (id, name, holder, acquired_at, locked_until)
            VALUES (gen_random_uuid(), :name, :holder, :now, :until)
            ON CONFLICT (name) DO UPDATE
              SET holder = EXCLUDED.holder, acquired_at = EXCLUDED.acquired_at, locked_until = EXCLUDED.locked_until
              WHERE job_locks.locked_until < :now
            RETURNING holder
            """
        ),
        {"name": name, "holder": holder, "now": now, "until": now + ttl},
    ).first()
    db.commit()
    return holder if row is not None else None


def release(db: Session, name: str, holder: str) -> None:
    db.execute(delete(JobLock).where(JobLock.name == name, JobLock.holder == holder))
    db.commit()


@contextmanager
def job_lock(db: Session, name: str, ttl: timedelta = timedelta(hours=1)) -> Iterator[str]:
    holder = try_acquire(db, name, ttl)
    if holder is None:
        raise LockNotAcquired(name)
    try:
        yield holder
    finally:
        db.rollback()
        release(db, name, holder)
