"""Exécution commune des jobs planifiés : logs début/fin, verrou, code de sortie."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging, log_event
from app.db.locks import LockNotAcquired, job_lock
from app.db.session import get_sessionmaker

EXIT_OK, EXIT_FAILED, EXIT_LOCKED = 0, 1, 0  # un job déjà en cours n'est pas une erreur


def run_job(name: str, func: Callable[[Session], dict[str, Any]], ttl: timedelta = timedelta(hours=1)) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger(f"app.jobs.{name}")
    problems = settings.check_production_ready()
    if problems:
        log_event(logger, "configuration invalide", logging.ERROR, problems=problems)
        return EXIT_FAILED
    started = time.monotonic()
    log_event(logger, "job start", job=name)
    db = get_sessionmaker()()
    try:
        with job_lock(db, name, ttl):
            result = func(db)
        log_event(
            logger,
            "job end",
            job=name,
            status="success",
            duration_s=round(time.monotonic() - started, 2),
            result=result,
        )
        return EXIT_OK
    except LockNotAcquired:
        log_event(logger, "job skipped: already running", logging.WARNING, job=name)
        return EXIT_LOCKED
    except Exception:
        logger.exception("job failed")
        log_event(
            logger, "job end", logging.ERROR, job=name, status="failed", duration_s=round(time.monotonic() - started, 2)
        )
        return EXIT_FAILED
    finally:
        db.close()


def main(name: str, func: Callable[[Session], dict[str, Any]], ttl: timedelta = timedelta(hours=1)) -> None:
    sys.exit(run_job(name, func, ttl))
