"""replace Run event metadata with versioned extensions

Revision ID: 202607230007
Revises: 202607230006
Create Date: 2026-07-23 23:50:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607230007"
down_revision: str | Sequence[str] | None = "202607230006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_EVENT_TYPES_WITH_HISTORICAL_METADATA = (
    "agent_model_started",
    "agent_model_completed",
    "agent_model_error",
    "tool_call_started",
    "tool_call_completed",
    "tool_call_error",
    "run_failed",
    "clarification_requested",
    "conflict_check_started",
    "conflict_check_completed",
    "context_compacted",
    "run_completed",
)


def upgrade() -> None:
    op.add_column(
        "agent_run_events",
        sa.Column("extension_kind", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "agent_run_events",
        sa.Column("extension_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "agent_run_events",
        sa.Column(
            "extension_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    known_types = ", ".join(
        f"'{event_type}'" for event_type in _EVENT_TYPES_WITH_HISTORICAL_METADATA
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM agent_run_events
                WHERE event_metadata <> '{{}}'::jsonb
                  AND event_type NOT IN ({known_types})
            ) THEN
                RAISE EXCEPTION
                    'agent_run_events contains an unclassified event_metadata payload';
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        UPDATE agent_run_events
        SET extension_kind = CASE
                WHEN event_metadata = '{}'::jsonb THEN NULL
                WHEN event_type IN (
                    'agent_model_started',
                    'agent_model_completed',
                    'agent_model_error'
                ) THEN 'north.model-call'
                WHEN event_type IN (
                    'tool_call_started',
                    'tool_call_completed',
                    'tool_call_error'
                ) THEN 'north.tool-call'
                WHEN event_type = 'run_failed' THEN 'agent-platform.failure'
                WHEN event_type = 'clarification_requested'
                     AND event_metadata ? 'state_version'
                THEN 'agent-platform.interaction-state'
                WHEN event_type IN ('conflict_check_started', 'conflict_check_completed')
                THEN 'dayboard.schedule-conflict-check'
                WHEN event_type = 'context_compacted' THEN 'north.context-compaction'
                ELSE NULL
            END,
            extension_payload = CASE
                WHEN event_type = 'clarification_requested'
                     AND event_metadata ? 'state_version'
                THEN jsonb_build_object('state_version', event_metadata -> 'state_version')
                WHEN event_type = 'run_completed' THEN '{}'::jsonb
                ELSE event_metadata
            END
        """
    )
    op.execute(
        """
        UPDATE agent_run_events
        SET extension_schema_version = 1
        WHERE extension_kind IS NOT NULL
        """
    )
    op.drop_column("agent_run_events", "event_metadata")
    op.create_check_constraint(
        "ck_agent_run_event_extension_schema_version",
        "agent_run_events",
        "extension_schema_version IS NULL OR extension_schema_version >= 1",
    )
    op.create_check_constraint(
        "ck_agent_run_event_extension_complete",
        "agent_run_events",
        "(extension_kind IS NULL AND extension_schema_version IS NULL "
        "AND extension_payload = '{}'::jsonb) OR "
        "(extension_kind IS NOT NULL AND char_length(extension_kind) > 0 "
        "AND extension_schema_version IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_run_event_extension_complete",
        "agent_run_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_run_event_extension_schema_version",
        "agent_run_events",
        type_="check",
    )
    op.add_column(
        "agent_run_events",
        sa.Column(
            "event_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE agent_run_events
        SET event_metadata = extension_payload
        WHERE extension_kind IS NOT NULL
        """
    )
    op.drop_column("agent_run_events", "extension_payload")
    op.drop_column("agent_run_events", "extension_schema_version")
    op.drop_column("agent_run_events", "extension_kind")
