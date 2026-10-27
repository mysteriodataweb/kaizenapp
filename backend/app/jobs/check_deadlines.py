"""Rappels J-14/J-7/J-3/J-1, tâches à faire et modifications significatives.

Usage : python -m app.jobs.check_deadlines
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs._runner import main
from app.models import User
from app.workers.notifications import service as notif


def run(db: Session) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for user in db.scalars(select(User).where(User.is_active.is_(True))).all():
        out[str(user.id)] = {
            "deadlines": [o.status for o in notif.send_deadline_reminders(db, user)],
            "tasks": [o.status for o in notif.send_task_reminders(db, user)],
            "changes": [o.status for o in notif.send_change_alerts(db, user)],
        }
    return out


if __name__ == "__main__":
    main("check_deadlines", run)
