"""Allow only one active run per conversation thread.

Revision ID: 202607100007
Revises: 202607100006
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607100007"
down_revision: str | None = "202607100006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_agent_runs_active_thread",
        "agent_runs",
        ["tenant_id", "thread_id"],
        unique=True,
        postgresql_where="status IN ('queued', 'running') AND deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_agent_runs_active_thread", table_name="agent_runs")
