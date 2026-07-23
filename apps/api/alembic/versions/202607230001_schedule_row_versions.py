"""add schedule row versions

Revision ID: 202607230001
Revises: 202607210001
Create Date: 2026-07-23 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607230001"
down_revision: str | Sequence[str] | None = "202607210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_entries",
        sa.Column("row_version", sa.BigInteger(), nullable=False, server_default="1"),
    )
    op.add_column(
        "task_items",
        sa.Column("row_version", sa.BigInteger(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("task_items", "row_version")
    op.drop_column("calendar_entries", "row_version")
