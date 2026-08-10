"""Unify conversation messages and Run events.

Revision ID: 7b2e4d9a1c30
Revises: 966685d63c93
Create Date: 2026-08-10 12:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7b2e4d9a1c30"
down_revision: str | Sequence[str] | None = "966685d63c93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("model_name", sa.String(160), nullable=True))
    op.add_column("agent_runs", sa.Column("error", sa.String(4000), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "agent_runs", sa.Column("first_human_message", sa.String(2000), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("last_ai_message", sa.String(2000), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        """
        UPDATE agent_runs
        SET first_human_message = left(input_message, 2000),
            last_ai_message = left(result_message, 2000),
            message_count = 1 + CASE WHEN result_message IS NULL THEN 0 ELSE 1 END,
            started_at = CASE WHEN status = 'queued' THEN NULL ELSE created_at END,
            completed_at = CASE
                WHEN status IN ('completed', 'needs_clarification', 'failed', 'cancelled')
                THEN updated_at
                ELSE NULL
            END
        """
    )

    op.add_column("agent_run_events", sa.Column("user_id", sa.UUID(), nullable=True))
    op.add_column("agent_run_events", sa.Column("thread_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE agent_run_events AS event
        SET user_id = run.user_id,
            thread_id = run.thread_id
        FROM agent_runs AS run
        WHERE run.id = event.run_id
        """
    )
    op.drop_index("ix_agent_run_events_user_run_created", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_user_run_seq", table_name="agent_run_events")
    op.execute(
        """
        INSERT INTO agent_run_events (
            id, user_id, thread_id, run_id, seq, event_type, category, content,
            extension_kind, extension_schema_version, extension_payload, created_at
        )
        SELECT
            id,
            user_id,
            thread_id,
            run_id,
            0,
            CASE role WHEN 'user' THEN 'message.human' ELSE 'message.ai' END,
            'message',
            content,
            presentation_kind,
            presentation_schema_version,
            presentation_payload,
            created_at
        FROM conversation_messages
        """
    )
    op.execute(
        """
        INSERT INTO agent_run_events (
            id, user_id, thread_id, run_id, seq, event_type, category, content,
            extension_kind, extension_schema_version, extension_payload, created_at
        )
        SELECT
            md5(run.id::text || '-agent-input')::uuid,
            run.user_id,
            run.thread_id,
            run.id,
            0,
            'agent.input',
            'model',
            run.input_message,
            NULL,
            NULL,
            '{}'::jsonb,
            run.created_at
        FROM agent_runs AS run
        JOIN conversation_messages AS message
          ON message.run_id = run.id
         AND message.user_id = run.user_id
         AND message.role = 'user'
        WHERE run.input_message <> message.content
        """
    )
    op.execute(
        """
        WITH ordered AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY thread_id
                    ORDER BY
                        created_at,
                        CASE event_type
                            WHEN 'message.human' THEN 0
                            WHEN 'message.ai' THEN 2
                            ELSE 1
                        END,
                        id
                ) AS new_seq
            FROM agent_run_events
        )
        UPDATE agent_run_events AS event
        SET seq = ordered.new_seq
        FROM ordered
        WHERE event.id = ordered.id
        """
    )
    op.alter_column("agent_run_events", "user_id", nullable=False)
    op.alter_column("agent_run_events", "thread_id", nullable=False)
    op.create_index(
        "uq_agent_run_events_thread_seq",
        "agent_run_events",
        ["thread_id", "seq"],
        unique=True,
    )
    op.create_index(
        "ix_agent_run_events_user_thread_category_seq",
        "agent_run_events",
        ["user_id", "thread_id", "category", "seq"],
    )
    op.create_index(
        "ix_agent_run_events_user_run_seq",
        "agent_run_events",
        ["user_id", "run_id", "seq"],
    )
    op.create_index(
        "uq_agent_run_events_message_role",
        "agent_run_events",
        ["user_id", "run_id", "event_type"],
        unique=True,
        postgresql_where=sa.text("event_type IN ('message.human', 'message.ai')"),
    )
    op.create_index(
        "uq_agent_run_events_execution_input",
        "agent_run_events",
        ["user_id", "run_id"],
        unique=True,
        postgresql_where=sa.text("event_type = 'agent.input'"),
    )

    op.drop_table("conversation_messages")
    op.drop_column("agent_runs", "result_message")
    op.drop_column("agent_runs", "input_message")


def downgrade() -> None:
    op.add_column(
        "agent_runs", sa.Column("input_message", sa.String(4000), nullable=True)
    )
    op.add_column(
        "agent_runs", sa.Column("result_message", sa.String(4000), nullable=True)
    )
    op.execute(
        """
        UPDATE agent_runs
        SET input_message = coalesce(
                (
                    SELECT event.content
                    FROM agent_run_events AS event
                    WHERE event.run_id = agent_runs.id
                      AND event.user_id = agent_runs.user_id
                      AND event.event_type = 'agent.input'
                    LIMIT 1
                ),
                first_human_message,
                ''
            ),
            result_message = last_ai_message
        """
    )
    op.alter_column("agent_runs", "input_message", nullable=False)

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.String(4000), nullable=False),
        sa.Column("presentation_kind", sa.String(80), nullable=True),
        sa.Column("presentation_schema_version", sa.Integer(), nullable=True),
        sa.Column(
            "presentation_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(presentation_kind IS NULL AND presentation_schema_version IS NULL "
            "AND presentation_payload = '{}'::jsonb) OR "
            "(presentation_kind IS NOT NULL AND presentation_schema_version IS NOT NULL)",
            name="ck_conversation_message_presentation_complete",
        ),
        sa.CheckConstraint(
            "presentation_kind IS NULL OR role = 'assistant'",
            name="ck_conversation_message_presentation_assistant_only",
        ),
        sa.CheckConstraint(
            "presentation_schema_version IS NULL OR presentation_schema_version >= 1",
            name="ck_conversation_message_presentation_schema_version",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO conversation_messages (
            id, user_id, thread_id, run_id, role, content,
            presentation_kind, presentation_schema_version, presentation_payload, created_at
        )
        SELECT
            id,
            user_id,
            thread_id,
            run_id,
            CASE event_type WHEN 'message.human' THEN 'user' ELSE 'assistant' END,
            content,
            extension_kind,
            extension_schema_version,
            extension_payload,
            created_at
        FROM agent_run_events
        WHERE event_type IN ('message.human', 'message.ai')
        """
    )
    op.create_index(
        "uq_conversation_messages_user_run_role",
        "conversation_messages",
        ["user_id", "run_id", "role"],
        unique=True,
    )

    op.execute(
        "DELETE FROM agent_run_events WHERE event_type IN ('message.human', 'message.ai')"
    )
    op.drop_index("uq_agent_run_events_execution_input", table_name="agent_run_events")
    op.drop_index("uq_agent_run_events_message_role", table_name="agent_run_events")
    op.drop_index("ix_agent_run_events_user_run_seq", table_name="agent_run_events")
    op.drop_index(
        "ix_agent_run_events_user_thread_category_seq", table_name="agent_run_events"
    )
    op.drop_index("uq_agent_run_events_thread_seq", table_name="agent_run_events")
    op.execute(
        """
        WITH ordered AS (
            SELECT
                id,
                row_number() OVER (PARTITION BY run_id ORDER BY seq, id) AS new_seq
            FROM agent_run_events
        )
        UPDATE agent_run_events AS event
        SET seq = ordered.new_seq
        FROM ordered
        WHERE event.id = ordered.id
        """
    )
    op.create_index(
        "ix_agent_run_events_user_run_created",
        "agent_run_events",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_agent_run_events_user_run_seq",
        "agent_run_events",
        ["run_id", "seq"],
        unique=True,
    )
    op.drop_column("agent_run_events", "thread_id")
    op.drop_column("agent_run_events", "user_id")

    op.drop_column("agent_runs", "completed_at")
    op.drop_column("agent_runs", "started_at")
    op.drop_column("agent_runs", "last_ai_message")
    op.drop_column("agent_runs", "first_human_message")
    op.drop_column("agent_runs", "message_count")
    op.drop_column("agent_runs", "error")
    op.drop_column("agent_runs", "model_name")
