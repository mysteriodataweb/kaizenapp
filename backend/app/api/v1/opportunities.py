from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import Match
from app.schemas.common import Page
from app.schemas.opportunity import FacetsOut, OpportunityDetail, OpportunityFilters, OpportunityListItem
from app.services import matching
from app.services import opportunities as service

router = APIRouter(tags=["opportunités"])


class FavoriteOut(BaseModel):
    opportunity_id: uuid.UUID
    is_favorite: bool


class MatchListItem(OpportunityListItem):
    satisfied: list[str] = []
    unsatisfied: list[str] = []
    unknown: list[str] = []
    to_complete: list[str] = []
    confidence_label: str | None = None


@router.get("/opportunities", response_model=Page[OpportunityListItem], summary="Catalogue filtré, trié et paginé")
def list_opportunities(
    filters: Annotated[OpportunityFilters, Query()], user: CurrentUser, db: DbSession
) -> Page[OpportunityListItem]:
    items, total = service.list_opportunities(db, user, filters)
    return Page(items=items, total=total, page=filters.page, page_size=filters.page_size)


@router.get("/opportunities/facets", response_model=FacetsOut)
def facets(user: CurrentUser, db: DbSession) -> FacetsOut:
    return service.facets(db)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDetail)
def get_opportunity(opportunity_id: uuid.UUID, user: CurrentUser, db: DbSession) -> OpportunityDetail:
    return service.get_detail(db, user, opportunity_id)


@router.post("/opportunities/{opportunity_id}/favorite", response_model=FavoriteOut)
def add_favorite(opportunity_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FavoriteOut:
    return FavoriteOut(opportunity_id=opportunity_id, is_favorite=service.set_favorite(db, user, opportunity_id, True))


@router.delete("/opportunities/{opportunity_id}/favorite", response_model=FavoriteOut)
def remove_favorite(opportunity_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FavoriteOut:
    return FavoriteOut(opportunity_id=opportunity_id, is_favorite=service.set_favorite(db, user, opportunity_id, False))


@router.get(
    "/matches", response_model=Page[MatchListItem], summary="Opportunités classées par compatibilité, avec explications"
)
def list_matches(
    filters: Annotated[OpportunityFilters, Query()], user: CurrentUser, db: DbSession
) -> Page[MatchListItem]:
    if filters.min_score is None:
        filters.min_score = 0
    items, total = service.list_opportunities(db, user, filters)
    expl: dict[uuid.UUID, dict[str, Any]] = {
        m.opportunity_id: m.explanation
        for m in db.scalars(
            select(Match).where(Match.user_id == user.id, Match.opportunity_id.in_([i.id for i in items]))
        )
    }
    out = []
    for item in items:
        e = expl.get(item.id, {})
        out.append(
            MatchListItem(
                **item.model_dump(),
                satisfied=(e.get("satisfied") or [])[:3],
                unsatisfied=(e.get("unsatisfied") or [])[:3],
                unknown=(e.get("unknown") or [])[:3],
                to_complete=e.get("to_complete") or [],
                confidence_label=e.get("confidence_label"),
            )
        )
    return Page(items=out, total=total, page=filters.page, page_size=filters.page_size)


class RecomputeOut(BaseModel):
    recomputed: int


@router.post("/matches/recompute", response_model=RecomputeOut, summary="Recalcule les scores de l'utilisateur")
def recompute(user: CurrentUser, db: DbSession, force: bool = False) -> RecomputeOut:
    count = matching.recompute_for_user(db, user, force=force)
    db.commit()
    return RecomputeOut(recomputed=count)
