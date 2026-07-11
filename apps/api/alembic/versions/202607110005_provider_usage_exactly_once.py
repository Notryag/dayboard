"""Make provider usage settlement idempotent per Run.

Revision ID: 202607110005
Revises: 202607110004
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607110005"
down_revision: str | None = "202607110004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM provider_usage_records
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY tenant_id, run_id
                        ORDER BY created_at DESC, id DESC
                    ) AS duplicate_number
                FROM provider_usage_records
            ) AS ranked_usage
            WHERE duplicate_number > 1
        )
        """
    )
    op.drop_index("ix_provider_usage_tenant_run", table_name="provider_usage_records")
    op.create_index(
        "uq_provider_usage_tenant_run",
        "provider_usage_records",
        ["tenant_id", "run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_provider_usage_tenant_run", table_name="provider_usage_records")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_provider_usage_tenant_run "
        "ON provider_usage_records (tenant_id, run_id)"
    )
