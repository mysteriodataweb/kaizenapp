"""Nettoyage : journaux anciens, sessions expirées, annonces échues ou périmées.

Usage : python -m app.jobs.cleanup_logs
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.jobs._runner import main
from app.models import IngestionRun, NotificationLog, Opportunity
from app.services.auth import cleanup_auth_tables


def run(db: Session) -> dict[str, Any]:
    now = utcnow()
    result: dict[str, Any] = {}
    result["notification_logs"] = db.execute(
        delete(NotificationLog).where(NotificationLog.created_at < now - timedelta(days=180))
    ).rowcount
    result["ingestion_runs"] = db.execute(
        delete(IngestionRun).where(IngestionRun.started_at < now - timedelta(days=90))
    ).rowcount
    # Date limite confirmée dépassée -> annonce close (jamais supprimée : historique des candidatures).
    result["closed_past_deadline"] = db.execute(
        update(Opportunity)
        .where(
            Opportunity.status == "open",
            Opportunity.deadline_status == "confirmed",
            Opportunity.deadline_at < now - timedelta(days=1),
        )
        .values(status="closed")
    ).rowcount
    result["marked_stale"] = db.execute(
        update(Opportunity)
        .where(Opportunity.last_seen_at < now - timedelta(days=30), Opportunity.verification_status != "stale")
        .values(verification_status="stale")
    ).rowcount
    db.commit()
    result.update(cleanup_auth_tables(db))
    return result


if __name__ == "__main__":
    main("cleanup_logs", run)
