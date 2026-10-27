"""Persistance des scores : recalcul quand le profil ou l'annonce change."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import utcnow
from app.models import Match, Opportunity, Profile, User
from app.workers.matching.engine import ENGINE_VERSION, OpportunityData, ProfileData, compute_match

logger = logging.getLogger("app.matching")


def _upsert(db: Session, user_id: uuid.UUID, profile: Profile, opp: Opportunity) -> None:
    result = compute_match(
        ProfileData.from_model(profile), OpportunityData.from_model(opp), get_settings().match_weights
    )
    values = {
        "user_id": user_id,
        "opportunity_id": opp.id,
        "eligibility": result.eligibility,
        "score": result.score,
        "confidence": result.confidence,
        "explanation": result.explanation,
        "missing_profile_fields": result.missing_profile_fields,
        "profile_version": profile.version,
        "opportunity_hash": opp.content_hash,
        "engine_version": result.engine_version,
        "computed_at": utcnow(),
    }
    stmt = insert(Match).values(**values)
    update_cols = {k: stmt.excluded[k] for k in values if k not in ("user_id", "opportunity_id")}
    db.execute(stmt.on_conflict_do_update(constraint="uq_matches_user_opportunity", set_=update_cols))


def recompute_for_user(db: Session, user: User, *, force: bool = False, batch: int = 500) -> int:
    """Recalcule uniquement les scores obsolètes (profil, annonce ou moteur modifiés)."""
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        return 0
    query = select(Opportunity).outerjoin(Match, and_(Match.opportunity_id == Opportunity.id, Match.user_id == user.id))
    if not force:
        query = query.where(
            or_(
                Match.id.is_(None),
                Match.profile_version != profile.version,
                Match.opportunity_hash != Opportunity.content_hash,
                Match.engine_version != ENGINE_VERSION,
            )
        )
    count = 0
    for opp in db.scalars(query.execution_options(yield_per=batch)):
        _upsert(db, user.id, profile, opp)
        count += 1
    db.flush()
    return count


def recompute_all(db: Session, *, force: bool = False) -> dict[str, int]:
    totals: dict[str, int] = {}
    for user in db.scalars(select(User).where(User.is_active.is_(True))).all():
        totals[str(user.id)] = recompute_for_user(db, user, force=force)
        db.commit()
    return totals


def ensure_match(db: Session, user: User, opp: Opportunity) -> Match | None:
    profile = db.scalar(select(Profile).where(Profile.user_id == user.id))
    if profile is None:
        return None
    match = db.scalar(select(Match).where(Match.user_id == user.id, Match.opportunity_id == opp.id))
    if (
        match is None
        or match.profile_version != profile.version
        or match.opportunity_hash != opp.content_hash
        or match.engine_version != ENGINE_VERSION
    ):
        _upsert(db, user.id, profile, opp)
        db.flush()
        match = db.scalar(
            select(Match)
            .where(Match.user_id == user.id, Match.opportunity_id == opp.id)
            .execution_options(populate_existing=True)
        )
    return match
