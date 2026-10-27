"""Indicateur d'urgence explicable (priorité de candidature)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.timeutil import days_until, utcnow


@dataclass
class Urgency:
    level: str  # expiree | critique | haute | moyenne | basse
    score: int
    reasons: list[str]
    days_left: int | None


def compute_urgency(
    *,
    deadline_at: datetime | None,
    deadline_status: str,
    eligibility: str | None,
    score: float | None,
    missing_documents: int,
    estimated_prep_hours: int | None,
    next_action_at: datetime | None,
    tz: str | None,
    now: datetime | None = None,
) -> Urgency:
    now = now or utcnow()
    reasons: list[str] = []
    points = 0
    days_left: int | None = None

    if deadline_at is None:
        points += 15
        reasons.append("Date limite inconnue : à vérifier sur la source officielle.")
    else:
        days_left = days_until(deadline_at, tz, now)
        suffix = " (date non vérifiée)" if deadline_status == "unverified" else ""
        if days_left < 0:
            return Urgency("expiree", 0, [f"Date limite dépassée depuis {-days_left} jour(s){suffix}."], days_left)
        for limit, pts in ((1, 50), (3, 45), (7, 38), (14, 28), (30, 15)):
            if days_left <= limit:
                points += pts
                break
        else:
            points += 5
        reasons.append(
            ("Échéance aujourd'hui" if days_left == 0 else f"Échéance dans {days_left} jour(s)") + suffix + "."
        )
        if estimated_prep_hours and days_left >= 0:
            per_day = estimated_prep_hours / max(days_left, 1)
            if per_day >= 3:
                points += 15
                reasons.append(f"Préparation serrée : ~{per_day:.1f} h/jour nécessaires.")

    if missing_documents:
        points += min(15, 5 * missing_documents)
        reasons.append(f"{missing_documents} document(s) exigé(s) non associé(s).")

    if eligibility == "ineligible":
        points -= 30
        reasons.append("Inéligible selon un critère publié.")
    elif eligibility == "unknown":
        reasons.append("Éligibilité à confirmer.")

    if score is not None:
        if score >= 75:
            points += 10
            reasons.append(f"Forte compatibilité ({score:.0f}/100).")
        elif score >= 50:
            points += 5

    if next_action_at is not None and next_action_at < now:
        points += 10
        reasons.append("Prochaine action en retard.")

    points = max(0, min(100, points))
    level = "critique" if points >= 70 else "haute" if points >= 45 else "moyenne" if points >= 25 else "basse"
    return Urgency(level, points, reasons, days_left)
