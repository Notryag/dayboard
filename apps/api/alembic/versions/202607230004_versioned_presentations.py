"""replace message metadata with versioned presentation envelopes

Revision ID: 202607230004
Revises: 202607230003
Create Date: 2026-07-23 20:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607230004"
down_revision: str | Sequence[str] | None = "202607230003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("presentation_kind", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "conversation_messages",
        sa.Column("presentation_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "presentation_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    # Historical snapshots predate row_version; migration 001 initialized those entities at 1.
    op.execute(
        """
        UPDATE conversation_messages
        SET presentation_kind = 'dayboard.schedule-results',
            presentation_schema_version = 1,
            presentation_payload = jsonb_build_object(
                'parts',
                CASE
                    WHEN jsonb_typeof(message_metadata::jsonb -> 'parts') = 'array'
                    THEN (
                        SELECT coalesce(
                            jsonb_agg(
                                CASE
                                    WHEN jsonb_typeof(part #> '{item,value}') = 'object'
                                         AND part #>> '{item,kind}' IN ('calendar', 'task')
                                    THEN jsonb_set(
                                        part,
                                        '{item,value,row_version}',
                                        coalesce(
                                            part #> '{item,value,row_version}',
                                            '1'::jsonb
                                        ),
                                        true
                                    )
                                    ELSE part
                                END
                                ORDER BY ordinal
                            ),
                            '[]'::jsonb
                        )
                        FROM jsonb_array_elements(
                            message_metadata::jsonb -> 'parts'
                        ) WITH ORDINALITY AS legacy_part(part, ordinal)
                    )
                    ELSE '[]'::jsonb
                END
            )
        WHERE role = 'assistant'
        """
    )
    op.drop_column("conversation_messages", "message_metadata")
    op.create_check_constraint(
        "ck_conversation_message_presentation_schema_version",
        "conversation_messages",
        "presentation_schema_version IS NULL OR presentation_schema_version >= 1",
    )
    op.create_check_constraint(
        "ck_conversation_message_presentation_complete",
        "conversation_messages",
        "(presentation_kind IS NULL AND presentation_schema_version IS NULL "
        "AND presentation_payload = '{}'::jsonb) OR "
        "(presentation_kind IS NOT NULL AND presentation_schema_version IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_conversation_message_presentation_assistant_only",
        "conversation_messages",
        "presentation_kind IS NULL OR role = 'assistant'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversation_message_presentation_assistant_only",
        "conversation_messages",
        type_="check",
    )
    op.drop_constraint(
        "ck_conversation_message_presentation_complete",
        "conversation_messages",
        type_="check",
    )
    op.drop_constraint(
        "ck_conversation_message_presentation_schema_version",
        "conversation_messages",
        type_="check",
    )
    op.add_column(
        "conversation_messages",
        sa.Column(
            "message_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE conversation_messages
        SET message_metadata = CASE
            WHEN presentation_kind = 'dayboard.schedule-results'
                 AND presentation_schema_version = 1
            THEN jsonb_build_object(
                'parts',
                CASE
                    WHEN jsonb_typeof(presentation_payload -> 'parts') = 'array'
                    THEN presentation_payload -> 'parts'
                    ELSE '[]'::jsonb
                END
            )
            ELSE '{}'::jsonb
        END
        """
    )
    op.drop_column("conversation_messages", "presentation_payload")
    op.drop_column("conversation_messages", "presentation_schema_version")
    op.drop_column("conversation_messages", "presentation_kind")
