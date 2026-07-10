"""Add durable product conversations.

Revision ID: 202607100005
Revises: 202607100004
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607100005"
down_revision: str | None = "202607100004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=8000), nullable=True),
        sa.Column("summary_through_message_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_threads_tenant_owner_updated",
        "conversation_threads",
        ["tenant_id", "owner_user_id", "updated_at"],
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.String(length=4000), nullable=False),
        sa.Column("message_metadata", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_messages_tenant_thread_created",
        "conversation_messages",
        ["tenant_id", "thread_id", "created_at"],
    )
    op.create_index(
        "uq_conversation_messages_tenant_run_role",
        "conversation_messages",
        ["tenant_id", "run_id", "role"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_conversation_messages_tenant_run_role", table_name="conversation_messages")
    op.drop_index("ix_conversation_messages_tenant_thread_created", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_conversation_threads_tenant_owner_updated", table_name="conversation_threads")
    op.drop_table("conversation_threads")
