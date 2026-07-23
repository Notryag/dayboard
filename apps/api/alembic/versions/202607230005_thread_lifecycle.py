"""separate conversation lifecycle from primary role

Revision ID: 202607230005
Revises: 202607230004
Create Date: 2026-07-23 22:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607230005"
down_revision: str | Sequence[str] | None = "202607230004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE conversation_threads SET status = 'active' WHERE status = 'isolated'"
    )
    op.create_check_constraint(
        "ck_conversation_thread_status",
        "conversation_threads",
        "status IN ('active', 'archived')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversation_thread_status",
        "conversation_threads",
        type_="check",
    )
    op.execute(
        "UPDATE conversation_threads SET status = 'isolated' "
        "WHERE status = 'active' AND is_primary IS FALSE"
    )
