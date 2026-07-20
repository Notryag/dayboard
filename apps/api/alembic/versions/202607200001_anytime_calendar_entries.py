"""add anytime calendar entries

Revision ID: 202607200001
Revises: 202607160001
Create Date: 2026-07-20 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607200001"
down_revision: str | Sequence[str] | None = "202607160001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_entries",
        sa.Column("timing_kind", sa.String(length=16), server_default="timed", nullable=False),
    )
    op.add_column("calendar_entries", sa.Column("scheduled_date", sa.Date(), nullable=True))
    op.alter_column("calendar_entries", "start_time", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.create_index(
        "ix_calendar_entries_tenant_owner_date",
        "calendar_entries",
        ["tenant_id", "owner_user_id", "scheduled_date"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_calendar_entries_timing_shape",
        "calendar_entries",
        "(timing_kind = 'timed' AND scheduled_date IS NULL AND start_time IS NOT NULL) OR "
        "(timing_kind = 'anytime' AND scheduled_date IS NOT NULL AND start_time IS NULL "
        "AND end_time IS NULL AND reminder IS NULL)",
    )
    op.alter_column("calendar_entries", "timing_kind", server_default=None)


def downgrade() -> None:
    op.drop_constraint("ck_calendar_entries_timing_shape", "calendar_entries", type_="check")
    op.drop_index("ix_calendar_entries_tenant_owner_date", table_name="calendar_entries")
    op.execute("DELETE FROM calendar_entries WHERE timing_kind = 'anytime'")
    op.alter_column("calendar_entries", "start_time", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.drop_column("calendar_entries", "scheduled_date")
    op.drop_column("calendar_entries", "timing_kind")
