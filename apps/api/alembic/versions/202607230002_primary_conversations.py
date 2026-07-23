"""make product conversations owner-scoped and primary

Revision ID: 202607230002
Revises: 202607230001
Create Date: 2026-07-23 10:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607230002"
down_revision: str | Sequence[str] | None = "202607230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        CREATE TEMP TABLE primary_conversation_map ON COMMIT DROP AS
        WITH activity AS (
            SELECT
                thread.id,
                thread.tenant_id,
                thread.owner_user_id,
                max(message.created_at) AS last_message_at,
                row_number() OVER (
                    PARTITION BY thread.tenant_id, thread.owner_user_id
                    ORDER BY max(message.created_at) DESC NULLS LAST,
                             thread.created_at DESC,
                             thread.id DESC
                ) AS position
            FROM conversation_threads AS thread
            LEFT JOIN conversation_messages AS message
              ON message.tenant_id = thread.tenant_id
             AND message.owner_user_id = thread.owner_user_id
             AND message.thread_id = thread.id
            WHERE thread.deleted_at IS NULL
            GROUP BY thread.id, thread.tenant_id, thread.owner_user_id, thread.created_at
        )
        SELECT
            activity.id AS old_thread_id,
            primary_thread.id AS primary_thread_id,
            activity.tenant_id,
            activity.owner_user_id,
            activity.position
        FROM activity
        JOIN activity AS primary_thread
          ON primary_thread.tenant_id = activity.tenant_id
         AND primary_thread.owner_user_id = activity.owner_user_id
         AND primary_thread.position = 1
        """
    )
    op.execute(
        """
        UPDATE conversation_messages AS message
           SET thread_id = mapping.primary_thread_id
          FROM primary_conversation_map AS mapping
         WHERE message.thread_id = mapping.old_thread_id
           AND mapping.position > 1
        """
    )
    op.execute(
        """
        UPDATE conversation_threads AS thread
           SET is_primary = (mapping.position = 1),
               status = CASE WHEN mapping.position = 1 THEN 'active' ELSE 'archived' END
          FROM primary_conversation_map AS mapping
         WHERE thread.id = mapping.old_thread_id
        """
    )
    op.create_index(
        "uq_conversation_threads_primary_owner",
        "conversation_threads",
        ["tenant_id", "owner_user_id"],
        unique=True,
        postgresql_where=sa.text("is_primary IS TRUE AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_conversation_threads_primary_owner", table_name="conversation_threads")
    op.drop_column("conversation_threads", "is_primary")
