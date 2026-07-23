"""replace untyped conversation state with versioned interactions

Revision ID: 202607230003
Revises: 202607230002
Create Date: 2026-07-23 18:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607230003"
down_revision: str | Sequence[str] | None = "202607230002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_states",
        sa.Column("interaction_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column("interaction_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column("interaction_source_run_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column("interaction_prompt", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column(
            "interaction_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE conversation_states SET expires_at = NULL, version = version + 1"
    )
    op.drop_column("conversation_states", "state_data")
    op.drop_column("conversation_states", "pending_question")
    op.drop_column("conversation_states", "pending_action")
    op.create_check_constraint(
        "ck_conversation_state_interaction_schema_version",
        "conversation_states",
        "interaction_schema_version IS NULL OR interaction_schema_version >= 1",
    )
    op.create_check_constraint(
        "ck_conversation_state_interaction_complete",
        "conversation_states",
        "(interaction_type IS NULL AND interaction_schema_version IS NULL "
        "AND interaction_source_run_id IS NULL AND interaction_prompt IS NULL "
        "AND interaction_payload = '{}'::jsonb AND expires_at IS NULL) OR "
        "(interaction_type IS NOT NULL AND interaction_schema_version IS NOT NULL "
        "AND interaction_source_run_id IS NOT NULL AND interaction_prompt IS NOT NULL "
        "AND expires_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversation_state_interaction_complete",
        "conversation_states",
        type_="check",
    )
    op.drop_constraint(
        "ck_conversation_state_interaction_schema_version",
        "conversation_states",
        type_="check",
    )
    op.add_column(
        "conversation_states",
        sa.Column("pending_action", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column("pending_question", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "conversation_states",
        sa.Column(
            "state_data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.drop_column("conversation_states", "interaction_payload")
    op.drop_column("conversation_states", "interaction_prompt")
    op.drop_column("conversation_states", "interaction_source_run_id")
    op.drop_column("conversation_states", "interaction_schema_version")
    op.drop_column("conversation_states", "interaction_type")
