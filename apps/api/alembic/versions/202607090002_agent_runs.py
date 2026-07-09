"""agent runs

Revision ID: 202607090002
Revises: 202607090001
Create Date: 2026-07-09 00:00:02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607090002"
down_revision: str | Sequence[str] | None = "202607090001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input_message", sa.String(length=4000), nullable=False),
        sa.Column("result_message", sa.String(length=4000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_runs_tenant_thread_created",
        "agent_runs",
        ["tenant_id", "thread_id", "created_at"],
    )
    op.create_index(
        "ix_agent_runs_tenant_owner_created",
        "agent_runs",
        ["tenant_id", "owner_user_id", "created_at"],
    )

    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("content", sa.String(length=4000), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_run_events_tenant_run_seq",
        "agent_run_events",
        ["tenant_id", "run_id", "seq"],
        unique=True,
    )
    op.create_index(
        "ix_agent_run_events_tenant_run_created",
        "agent_run_events",
        ["tenant_id", "run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_run_events_tenant_run_created", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_tenant_run_seq", table_name="agent_run_events")
    op.drop_table("agent_run_events")
    op.drop_index("ix_agent_runs_tenant_owner_created", table_name="agent_runs")
    op.drop_index("ix_agent_runs_tenant_thread_created", table_name="agent_runs")
    op.drop_table("agent_runs")
