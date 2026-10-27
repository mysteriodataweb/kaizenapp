from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.timeutil import utcnow
from app.models import Application, Favorite, Match, Opportunity, OpportunitySource, Source, User
from app.schemas.opportunity import (
    FacetsOut,
    MatchSummary,
    OpportunityDetail,
    OpportunityFilters,
    OpportunityListItem,
    SourceRef,
)
from app.services import matching


def _base_query(user: User) -> Select[Any]:
    return (
        select(
            Opportunity,
            Match,
            Application.id.label("application_id"),
            Application.status.label("application_status"),
            Favorite.user_id.label("favorite_user"),
        )
        .outerjoin(Match, and_(Match.opportunity_id == Opportunity.id, Match.user_id == user.id))
        .outerjoin(Application, and_(Application.opportunity_id == Opportunity.id, Application.user_id == user.id))
        .outerjoin(Favorite, and_(Favorite.opportunity_id == Opportunity.id, Favorite.user_id == user.id))
    )


def _apply_filters(query: Select[Any], f: OpportunityFilters) -> Select[Any]:
    now = utcnow()
    if f.q:
        like = f"%{f.q.strip()}%"
        query = query.where(
            or_(
                Opportunity.search_vector.op("@@")(func.websearch_to_tsquery("simple", f.q)),
                Opportunity.title.ilike(like),
                Opportunity.organization.ilike(like),
            )
        )
    if f.type:
        query = query.where(Opportunity.type == f.type)
    if f.country:
        query = query.where(Opportunity.countries.contains([f.country.upper()]))
    if f.field:
        like = f"%{f.field.strip()}%"
        query = query.where(
            or_(func.array_to_string(Opportunity.fields, " ").ilike(like), Opportunity.title.ilike(like))
        )
    if f.organization:
        query = query.where(Opportunity.organization.ilike(f"%{f.organization.strip()}%"))
    if f.study_level:
        # Inclut les annonces qui ne précisent pas de niveau (elles peuvent vous concerner).
        query = query.where(
            or_(Opportunity.study_levels.contains([f.study_level]), func.cardinality(Opportunity.study_levels) == 0)
        )
    if f.funding == "full":
        query = query.where(Opportunity.funding_type == "full")
    elif f.funding == "partial":
        query = query.where(Opportunity.funding_type == "partial")
    elif f.funding == "full_or_partial":
        query = query.where(Opportunity.funding_type.in_(("full", "partial")))
    if f.deadline_within_days:
        query = query.where(
            Opportunity.deadline_at.is_not(None),
            Opportunity.deadline_at >= now,
            Opportunity.deadline_at <= now + timedelta(days=f.deadline_within_days),
        )
    if not f.include_closed:
        query = query.where(
            Opportunity.status != "closed",
            or_(Opportunity.deadline_at.is_(None), Opportunity.deadline_at >= now),
        )
    if f.eligibility:
        query = query.where(Match.eligibility == f.eligibility)
    if f.min_score is not None:
        query = query.where(Match.score >= f.min_score)
    if f.application_status:
        query = query.where(Application.status == f.application_status)
    if f.tracked is True:
        query = query.where(Application.id.is_not(None))
    elif f.tracked is False:
        query = query.where(Application.id.is_(None))
    if f.favorites_only:
        query = query.where(Favorite.user_id.is_not(None))
    return query


def _order(query: Select[Any], sort: str) -> Select[Any]:
    orders = {
        "deadline": [Opportunity.deadline_at.asc().nulls_last()],
        "-deadline": [Opportunity.deadline_at.desc().nulls_last()],
        "score": [Match.score.asc().nulls_last()],
        "-score": [Match.score.desc().nulls_last(), Opportunity.deadline_at.asc().nulls_last()],
        "recent": [Opportunity.first_seen_at.desc()],
        "title": [Opportunity.title.asc()],
    }
    return query.order_by(*orders.get(sort, orders["-score"]), Opportunity.id)


def _list_item(row: Any) -> OpportunityListItem:
    opp, match = row[0], row[1]
    item = OpportunityListItem.model_validate(opp)
    item.is_favorite = row.favorite_user is not None
    item.application_id = row.application_id
    item.application_status = row.application_status
    if match is not None:
        item.match = MatchSummary(
            eligibility=match.eligibility, score=match.score, confidence=match.confidence, computed_at=match.computed_at
        )
    return item


def list_opportunities(db: Session, user: User, f: OpportunityFilters) -> tuple[list[OpportunityListItem], int]:
    query = _apply_filters(_base_query(user), f)
    total = db.scalar(select(func.count()).select_from(query.with_only_columns(Opportunity.id).subquery())) or 0
    rows = db.execute(_order(query, f.sort).limit(f.page_size).offset((f.page - 1) * f.page_size)).all()
    return [_list_item(r) for r in rows], total


def get_opportunity(db: Session, opportunity_id: uuid.UUID) -> Opportunity:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise NotFound("Opportunité introuvable.")
    return opp


def get_detail(db: Session, user: User, opportunity_id: uuid.UUID) -> OpportunityDetail:
    opp = get_opportunity(db, opportunity_id)
    match = matching.ensure_match(db, user, opp)
    db.commit()
    row = db.execute(_base_query(user).where(Opportunity.id == opp.id)).first()
    base = _list_item(row)
    detail = OpportunityDetail.model_validate(opp)
    for key in ("is_favorite", "application_id", "application_status", "match"):
        setattr(detail, key, getattr(base, key))
    detail.match_detail = match.explanation if match else None
    sources = db.execute(
        select(OpportunitySource, Source)
        .join(Source, Source.id == OpportunitySource.source_id)
        .where(OpportunitySource.opportunity_id == opp.id)
        .order_by(OpportunitySource.first_seen_at)
    ).all()
    detail.sources = [
        SourceRef(
            source_key=src.key,
            source_name=src.name,
            source_url=os.source_url,
            first_seen_at=os.first_seen_at,
            last_seen_at=os.last_seen_at,
        )
        for os, src in sources
    ]
    return detail


def set_favorite(db: Session, user: User, opportunity_id: uuid.UUID, favorite: bool) -> bool:
    get_opportunity(db, opportunity_id)
    if favorite:
        db.execute(insert(Favorite).values(user_id=user.id, opportunity_id=opportunity_id).on_conflict_do_nothing())
    else:
        db.query(Favorite).filter_by(user_id=user.id, opportunity_id=opportunity_id).delete()
    db.commit()
    return favorite


def facets(db: Session) -> FacetsOut:
    country_rows = db.execute(
        text("SELECT DISTINCT unnest(countries) AS c FROM opportunities WHERE status <> 'closed' ORDER BY c")
    ).all()
    field_rows = db.execute(
        text(
            "SELECT f, count(*) FROM (SELECT unnest(fields) AS f FROM opportunities WHERE status <> 'closed') s "
            "GROUP BY f ORDER BY count(*) DESC, f LIMIT 60"
        )
    ).all()
    org_rows = db.execute(
        select(Opportunity.organization, func.count())
        .where(Opportunity.status != "closed")
        .group_by(Opportunity.organization)
        .order_by(func.count().desc(), Opportunity.organization)
        .limit(60)
    ).all()
    type_rows = db.execute(select(Opportunity.type).distinct().order_by(Opportunity.type)).all()
    return FacetsOut(
        countries=[r[0] for r in country_rows],
        fields=[r[0] for r in field_rows],
        organizations=[r[0] for r in org_rows],
        types=[r[0] for r in type_rows],
    )
