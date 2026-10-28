"""offres privées (ajoutées par lien, visibles de leur seul auteur)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("owner_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_opportunities_owner_user_id_users"),
        "opportunities",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("uq_opportunities_canonical_url"), "opportunities", type_="unique")
    op.create_index(
        "uq_opportunities_canonical_public",
        "opportunities",
        ["canonical_url"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NULL"),
    )
    op.create_index(
        "uq_opportunities_owner_canonical",
        "opportunities",
        ["owner_user_id", "canonical_url"],
        unique=True,
        postgresql_where=sa.text("owner_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Les offres privées n'ont pas d'équivalent dans l'ancien schéma (URL unique globale) : elles sont retirées.
    op.execute("DELETE FROM opportunities WHERE owner_user_id IS NOT NULL")
    op.drop_index("uq_opportunities_owner_canonical", table_name="opportunities")
    op.drop_index("uq_opportunities_canonical_public", table_name="opportunities")
    op.create_unique_constraint(op.f("uq_opportunities_canonical_url"), "opportunities", ["canonical_url"])
    op.drop_constraint(op.f("fk_opportunities_owner_user_id_users"), "opportunities", type_="foreignkey")
    op.drop_column("opportunities", "owner_user_id")
