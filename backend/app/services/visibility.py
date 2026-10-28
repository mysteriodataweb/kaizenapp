"""Visibilité des offres : catalogue commun + offres privées de l'utilisateur (ajoutées par lien)."""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, or_

from app.models import Opportunity


def visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Opportunity.owner_user_id.is_(None), Opportunity.owner_user_id == user_id)


def is_visible(opp: Opportunity, user_id: uuid.UUID) -> bool:
    return opp.owner_user_id is None or opp.owner_user_id == user_id
