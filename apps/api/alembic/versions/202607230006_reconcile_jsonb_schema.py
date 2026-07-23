"""reconcile legacy json columns with jsonb metadata

Revision ID: 202607230006
Revises: 202607230005
Create Date: 2026-07-23 23:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "202607230006"
down_revision: str | Sequence[str] | None = "202607230005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_JSON_COLUMNS = (
    ("agent_run_events", "event_metadata", False, "'{}'::jsonb"),
    ("calendar_entries", "participants", False, "'[]'::jsonb"),
    ("calendar_entries", "reminder", True, None),
    ("provider_usage_records", "usage_metadata", False, "'{}'::jsonb"),
    ("task_items", "reminder", True, None),
)


def upgrade() -> None:
    for table_name, column_name, nullable, server_default in _JSON_COLUMNS:
        if server_default is not None:
            op.alter_column(table_name, column_name, server_default=None)
        op.alter_column(
            table_name,
            column_name,
            existing_type=postgresql.JSON(astext_type=sa.Text()),
            type_=postgresql.JSONB(astext_type=sa.Text()),
            existing_nullable=nullable,
            postgresql_using=f"{column_name}::jsonb",
        )
        if server_default is not None:
            op.alter_column(
                table_name,
                column_name,
                existing_type=postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text(server_default),
            )


def downgrade() -> None:
    for table_name, column_name, nullable, server_default in reversed(_JSON_COLUMNS):
        if server_default is not None:
            op.alter_column(table_name, column_name, server_default=None)
        op.alter_column(
            table_name,
            column_name,
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            type_=postgresql.JSON(astext_type=sa.Text()),
            existing_nullable=nullable,
            postgresql_using=f"{column_name}::json",
        )
        if server_default is not None:
            op.alter_column(
                table_name,
                column_name,
                existing_type=postgresql.JSON(astext_type=sa.Text()),
                server_default=sa.text(server_default.replace("::jsonb", "::json")),
            )
