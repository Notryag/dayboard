"""initial schema

Revision ID: 202607090001
Revises:
Create Date: 2026-07-09 00:00:01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607090001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("reminder", sa.JSON(), nullable=True),
        sa.Column("created_by_run_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_calendar_entries_tenant_owner_start",
        "calendar_entries",
        ["tenant_id", "owner_user_id", "start_time"],
    )
    op.create_index(
        "ix_calendar_entries_tenant_start",
        "calendar_entries",
        ["tenant_id", "start_time"],
    )
    op.create_index(
        "ix_calendar_entries_tenant_created_by_run",
        "calendar_entries",
        ["tenant_id", "created_by_run_id"],
    )

    op.create_table(
        "task_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("reminder", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_run_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_items_tenant_owner_status_due",
        "task_items",
        ["tenant_id", "owner_user_id", "status", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_items_tenant_owner_status_due", table_name="task_items")
    op.drop_table("task_items")
    op.drop_index("ix_calendar_entries_tenant_created_by_run", table_name="calendar_entries")
    op.drop_index("ix_calendar_entries_tenant_start", table_name="calendar_entries")
    op.drop_index("ix_calendar_entries_tenant_owner_start", table_name="calendar_entries")
    op.drop_table("calendar_entries")
