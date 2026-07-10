"""provider usage records

Revision ID: 202607100001
Revises: 202607090002
Create Date: 2026-07-10 00:00:01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607100001"
down_revision: str | Sequence[str] | None = "202607090002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=240), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("usage_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_usage_tenant_user_created",
        "provider_usage_records",
        ["tenant_id", "owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_provider_usage_tenant_run",
        "provider_usage_records",
        ["tenant_id", "run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_usage_tenant_run", table_name="provider_usage_records")
    op.drop_index("ix_provider_usage_tenant_user_created", table_name="provider_usage_records")
    op.drop_table("provider_usage_records")
