"""Allow multiple create operations in one agent run.

Revision ID: 202607110001
Revises: 202607100007
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607110001"
down_revision: str | None = "202607100007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_entries",
        sa.Column("created_operation_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "task_items",
        sa.Column("created_operation_key", sa.String(length=64), nullable=True),
    )
    op.drop_index("uq_calendar_entries_tenant_created_by_run", table_name="calendar_entries")
    op.drop_index("uq_task_items_tenant_created_by_run", table_name="task_items")
    op.create_index(
        "uq_calendar_entries_tenant_run_create_operation",
        "calendar_entries",
        ["tenant_id", "created_by_run_id", "created_operation_key"],
        unique=True,
        postgresql_where=(
            "created_by_run_id IS NOT NULL AND created_operation_key IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_task_items_tenant_run_create_operation",
        "task_items",
        ["tenant_id", "created_by_run_id", "created_operation_key"],
        unique=True,
        postgresql_where=(
            "created_by_run_id IS NOT NULL AND created_operation_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_task_items_tenant_run_create_operation", table_name="task_items")
    op.drop_index(
        "uq_calendar_entries_tenant_run_create_operation",
        table_name="calendar_entries",
    )
    op.create_index(
        "uq_task_items_tenant_created_by_run",
        "task_items",
        ["tenant_id", "created_by_run_id"],
        unique=True,
        postgresql_where="created_by_run_id IS NOT NULL",
    )
    op.create_index(
        "uq_calendar_entries_tenant_created_by_run",
        "calendar_entries",
        ["tenant_id", "created_by_run_id"],
        unique=True,
        postgresql_where="created_by_run_id IS NOT NULL",
    )
    op.drop_column("task_items", "created_operation_key")
    op.drop_column("calendar_entries", "created_operation_key")
