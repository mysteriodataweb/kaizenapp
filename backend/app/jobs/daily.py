"""Option économique : un seul Cron Job Render qui enchaîne toutes les tâches quotidiennes.

Collecte -> recalcul des scores -> rappels/tâches/modifications -> récapitulatif -> nettoyage.
Chaque étape est isolée : l'échec de l'une n'empêche pas les suivantes.

Usage : python -m app.jobs.daily
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.jobs import check_deadlines, cleanup_logs, send_digest
from app.jobs._runner import main
from app.jobs.collect_opportunities import collect
from app.services import matching

logger = logging.getLogger("app.jobs.daily")


def run(db: Session) -> dict[str, Any]:
    steps = {
        "collect": lambda: collect(db),
        "recompute": lambda: {"recomputed": sum(matching.recompute_all(db).values())},
        "deadlines": lambda: check_deadlines.run(db),
        "digest": lambda: send_digest.run(db),
        "cleanup": lambda: cleanup_logs.run(db),
    }
    results: dict[str, Any] = {}
    failures = []
    for name, step in steps.items():
        try:
            results[name] = step()
        except Exception:
            db.rollback()
            logger.exception("daily step failed: %s", name)
            failures.append(name)
    if failures:
        raise RuntimeError(f"Étapes en échec : {', '.join(failures)}")
    return results


if __name__ == "__main__":
    main("daily", run, ttl=timedelta(hours=3))
