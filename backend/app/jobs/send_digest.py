"""Récapitulatif quotidien/hebdomadaire (à lancer toutes les heures : chaque utilisateur
reçoit son résumé à l'heure locale choisie, une seule fois par période).

Usage : python -m app.jobs.send_digest
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs._runner import main
from app.models import User
from app.workers.notifications import service as notif


def run(db: Session) -> dict[str, Any]:
    return {
        str(u.id): notif.send_digest(db, u).status
        for u in db.scalars(select(User).where(User.is_active.is_(True))).all()
    }


if __name__ == "__main__":
    main("send_digest", run)
