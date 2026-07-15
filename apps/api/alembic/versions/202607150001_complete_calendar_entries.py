"""add calendar completion state

Revision ID: 202607150001
Revises: 202607140001
Create Date: 2026-07-15 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607150001"
down_revision: str | Sequence[str] | None = "202607140001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "calendar_entries",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calendar_entries", "completed_at")
