"""inscription publique : confirmation de l'adresse e-mail

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

OLD_KINDS = "'new_matches', 'digest', 'deadline', 'task', 'change', 'ingestion_error', 'password_reset', 'test'"
NEW_KINDS = (
    "'new_matches', 'digest', 'deadline', 'task', 'change', 'ingestion_error', 'password_reset', "
    "'email_verification', 'registration_existing', 'test'"
)

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    # Comptes existants : créés par l'administrateur (CLI / amorçage), donc considérés comme confirmés.
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")
    op.create_table(
        "email_verification_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_verification_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verification_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_verification_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_email_verification_tokens_user_id"), "email_verification_tokens", ["user_id"], unique=False
    )
    op.drop_constraint(op.f("ck_notification_logs_kind_valid"), "notification_logs", type_="check")
    op.create_check_constraint(op.f("ck_notification_logs_kind_valid"), "notification_logs", f"kind IN ({NEW_KINDS})")


def downgrade() -> None:
    op.execute("DELETE FROM notification_logs WHERE kind IN ('email_verification', 'registration_existing')")
    op.drop_constraint(op.f("ck_notification_logs_kind_valid"), "notification_logs", type_="check")
    op.create_check_constraint(op.f("ck_notification_logs_kind_valid"), "notification_logs", f"kind IN ({OLD_KINDS})")
    op.drop_index(op.f("ix_email_verification_tokens_user_id"), table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified_at")
