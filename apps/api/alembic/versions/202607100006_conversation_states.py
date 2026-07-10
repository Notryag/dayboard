"""Add structured conversation state.

Revision ID: 202607100006
Revises: 202607100005
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607100006"
down_revision: str | None = "202607100005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_states",
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("pending_action", sa.String(length=80), nullable=True),
        sa.Column("pending_question", sa.String(length=1000), nullable=True),
        sa.Column("state_data", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("thread_id"),
    )


def downgrade() -> None:
    op.drop_table("conversation_states")
