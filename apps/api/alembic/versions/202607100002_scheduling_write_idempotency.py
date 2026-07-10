"""scheduling write idempotency

Revision ID: 202607100002
Revises: 202607100001
Create Date: 2026-07-10 00:00:02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607100002"
down_revision: str | Sequence[str] | None = "202607100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_calendar_entries_tenant_created_by_run",
        "calendar_entries",
        ["tenant_id", "created_by_run_id"],
        unique=True,
        postgresql_where="created_by_run_id IS NOT NULL",
    )
    op.create_index(
        "uq_task_items_tenant_created_by_run",
        "task_items",
        ["tenant_id", "created_by_run_id"],
        unique=True,
        postgresql_where="created_by_run_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_task_items_tenant_created_by_run", table_name="task_items")
    op.drop_index("uq_calendar_entries_tenant_created_by_run", table_name="calendar_entries")
