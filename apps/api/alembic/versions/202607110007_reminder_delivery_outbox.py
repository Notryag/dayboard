"""Add reminder delivery outbox.

Revision ID: 202607110007
Revises: 202607110006
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607110007"
down_revision: str | None = "202607110006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(240), nullable=True),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_reminder_deliveries_active_source_channel",
        "reminder_deliveries",
        ["tenant_id", "source_type", "source_id", "channel"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing') AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_reminder_deliveries_due",
        "reminder_deliveries",
        ["status", "next_attempt_at", "scheduled_for"],
    )
    op.create_index(
        "ix_reminder_deliveries_tenant_owner_created",
        "reminder_deliveries",
        ["tenant_id", "owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("reminder_deliveries")
