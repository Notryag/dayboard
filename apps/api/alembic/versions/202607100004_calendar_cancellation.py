"""Add reliable calendar cancellation metadata.

Revision ID: 202607100004
Revises: 202607100003
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607100004"
down_revision: str | None = "202607100003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_entries",
        sa.Column("cancelled_by_run_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "calendar_entries",
        sa.Column("cancellation_reason", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_calendar_entries_tenant_cancelled_by_run",
        "calendar_entries",
        ["tenant_id", "cancelled_by_run_id"],
    )
    op.create_index(
        "uq_calendar_entries_tenant_cancelled_by_run",
        "calendar_entries",
        ["tenant_id", "cancelled_by_run_id"],
        unique=True,
        postgresql_where=sa.text("cancelled_by_run_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_calendar_entries_tenant_cancelled_by_run",
        table_name="calendar_entries",
    )
    op.drop_index(
        "ix_calendar_entries_tenant_cancelled_by_run",
        table_name="calendar_entries",
    )
    op.drop_column("calendar_entries", "cancellation_reason")
    op.drop_column("calendar_entries", "cancelled_by_run_id")
