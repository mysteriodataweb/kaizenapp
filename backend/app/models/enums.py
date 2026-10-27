"""Valeurs autorisées (contraintes CHECK en base + validation Pydantic).

Des colonnes VARCHAR + CHECK sont préférées aux ENUM natifs PostgreSQL : l'ajout
d'une valeur reste une migration simple et non bloquante.
"""

from __future__ import annotations

from enum import StrEnum


class OpportunityType(StrEnum):
    INTERNSHIP = "internship"
    MASTERS_SCHOLARSHIP = "masters_scholarship"


class StudyLevel(StrEnum):
    SECONDARY = "secondary"
    BACHELOR = "bachelor"
    MASTER = "master"
    DOCTORATE = "doctorate"
    OTHER = "other"


class FundingType(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class FundingPreference(StrEnum):
    FULL_ONLY = "full_only"
    FULL_OR_PARTIAL = "full_or_partial"
    ANY = "any"


class DeadlineStatus(StrEnum):
    CONFIRMED = "confirmed"  # publiée explicitement par la source officielle
    UNVERIFIED = "unverified"  # trouvée mais non confirmée (ex. agrégateur)
    UNKNOWN = "unknown"  # aucune date connue


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    STALE = "stale"


class PublicationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class Eligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNKNOWN = "unknown"


class ApplicationStatus(StrEnum):
    TO_EXPLORE = "to_explore"
    TO_PREPARE = "to_prepare"
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    SELECTION = "selection"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


ACTIVE_APPLICATION_STATUSES = (
    ApplicationStatus.TO_EXPLORE,
    ApplicationStatus.TO_PREPARE,
    ApplicationStatus.PREPARING,
)
FINAL_APPLICATION_STATUSES = (
    ApplicationStatus.ACCEPTED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
)


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class DocumentType(StrEnum):
    CV = "cv"
    COVER_LETTER = "cover_letter"
    TRANSCRIPT = "transcript"
    DIPLOMA = "diploma"
    LANGUAGE_CERTIFICATE = "language_certificate"
    RECOMMENDATION_LETTER = "recommendation_letter"
    ESSAY = "essay"
    OTHER = "other"


class SourceVerification(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILING = "failing"


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationKind(StrEnum):
    NEW_MATCHES = "new_matches"
    DIGEST = "digest"
    DEADLINE = "deadline"
    TASK = "task"
    CHANGE = "change"
    INGESTION_ERROR = "ingestion_error"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"
    REGISTRATION_EXISTING = "registration_existing"
    TEST = "test"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    SIMULATED = "simulated"
    FAILED = "failed"
    SKIPPED = "skipped"


class DigestFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    NEVER = "never"


CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2", "native")


def check_in(column: str, values: type[StrEnum] | tuple[str, ...]) -> str:
    """Construit l'expression SQL d'une contrainte CHECK `column IN (...)`."""
    items = [v.value for v in values] if isinstance(values, type) else list(values)
    quoted = ", ".join(f"'{v}'" for v in items)
    return f"{column} IN ({quoted})"
