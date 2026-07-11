"""Add idempotent task updates.

Revision ID: 202607110003
Revises: 202607110002
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607110003"
down_revision: str | None = "202607110002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "task_items", sa.Column("updated_operation_key", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "uq_task_items_tenant_run_update_operation",
        "task_items",
        ["tenant_id", "updated_by_run_id", "updated_operation_key"],
        unique=True,
        postgresql_where=sa.text(
            "updated_by_run_id IS NOT NULL AND updated_operation_key IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_task_items_tenant_run_update_operation", table_name="task_items")
    op.drop_column("task_items", "updated_operation_key")
