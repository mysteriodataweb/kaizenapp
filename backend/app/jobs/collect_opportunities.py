"""Collecte quotidienne : sources activées -> recalcul des scores -> alertes « nouvelles opportunités ».

Usage : python -m app.jobs.collect_opportunities [--source KEY]
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs._runner import main
from app.models import Source, User
from app.services import matching
from app.workers.ingestion import run_source
from app.workers.notifications import service as notif


def collect(db: Session, source_key: str | None = None, triggered_by: str = "cron") -> dict[str, Any]:
    query = select(Source).where(Source.enabled.is_(True)).order_by(Source.key)
    if source_key:
        query = select(Source).where(Source.key == source_key)
    results: dict[str, Any] = {}
    for source in db.scalars(query).all():
        run = run_source(db, source, triggered_by=triggered_by)  # les erreurs d'une source n'arrêtent pas les autres
        results[source.key] = {"status": run.status, "created": run.items_created, "updated": run.items_updated}
    recomputed = matching.recompute_all(db)
    db.commit()
    alerts = {}
    for user in db.scalars(select(User).where(User.is_active.is_(True))).all():
        alerts[str(user.id)] = notif.send_new_matches(db, user).status
    notif.send_ingestion_alerts(db)
    return {"sources": results, "recomputed": sum(recomputed.values()), "alerts": alerts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Clé d'une source précise (même désactivée)")
    args = parser.parse_args()
    main("collect_opportunities", lambda db: collect(db, args.source), ttl=timedelta(hours=2))
