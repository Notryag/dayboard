"""Add per-operation calendar update idempotency.

Revision ID: 202607110004
Revises: 202607110003
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607110004"
down_revision: str | None = "202607110003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_entries",
        sa.Column("updated_operation_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "calendar_entries",
        sa.Column("cancelled_operation_key", sa.String(length=64), nullable=True),
    )
    op.drop_index(
        "uq_calendar_entries_tenant_cancelled_by_run",
        table_name="calendar_entries",
    )
    op.create_index(
        "uq_calendar_entries_tenant_run_update_operation",
        "calendar_entries",
        ["tenant_id", "updated_by_run_id", "updated_operation_key"],
        unique=True,
        postgresql_where=sa.text(
            "updated_by_run_id IS NOT NULL AND updated_operation_key IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_calendar_entries_tenant_run_cancel_operation",
        "calendar_entries",
        ["tenant_id", "cancelled_by_run_id", "cancelled_operation_key"],
        unique=True,
        postgresql_where=sa.text(
            "cancelled_by_run_id IS NOT NULL AND cancelled_operation_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_calendar_entries_tenant_run_cancel_operation",
        table_name="calendar_entries",
    )
    op.drop_index(
        "uq_calendar_entries_tenant_run_update_operation",
        table_name="calendar_entries",
    )
    op.create_index(
        "uq_calendar_entries_tenant_cancelled_by_run",
        "calendar_entries",
        ["tenant_id", "cancelled_by_run_id"],
        unique=True,
        postgresql_where=sa.text("cancelled_by_run_id IS NOT NULL"),
    )
    op.drop_column("calendar_entries", "cancelled_operation_key")
    op.drop_column("calendar_entries", "updated_operation_key")
