"""Dates : stockage en UTC, interprétation dans le fuseau de l'utilisateur."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utcnow() -> datetime:
    return datetime.now(UTC)


def safe_zone(tz: str | None, fallback: str = "Europe/Paris") -> ZoneInfo:
    for candidate in (tz, fallback, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo("UTC")


def is_valid_timezone(tz: str) -> bool:
    try:
        ZoneInfo(tz)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def local_date(dt: datetime, tz: str | None) -> date:
    return dt.astimezone(safe_zone(tz)).date()


def days_until(deadline: datetime, tz: str | None, now: datetime | None = None) -> int:
    """Nombre de jours calendaires (dans le fuseau utilisateur) avant l'échéance."""
    now = now or utcnow()
    return (local_date(deadline, tz) - local_date(now, tz)).days


def end_of_day(d: date, tz: str | None) -> datetime:
    """Fin de journée locale (23:59:59) convertie en UTC — utile pour une date limite sans heure."""
    return datetime.combine(d, time(23, 59, 59), tzinfo=safe_zone(tz)).astimezone(UTC)


def ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
