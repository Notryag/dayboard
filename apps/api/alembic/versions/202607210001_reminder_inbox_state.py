"""add reminder inbox state

Revision ID: 202607210001
Revises: 202607200001
Create Date: 2026-07-21 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607210001"
down_revision: str | Sequence[str] | None = "202607200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reminder_deliveries",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_reminder_deliveries_tenant_owner_unread",
        "reminder_deliveries",
        ["tenant_id", "owner_user_id", "read_at"],
        unique=False,
        postgresql_where=sa.text("status = 'delivered' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reminder_deliveries_tenant_owner_unread",
        table_name="reminder_deliveries",
    )
    op.drop_column("reminder_deliveries", "read_at")
