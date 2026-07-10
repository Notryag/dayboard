"""command idempotency keys

Revision ID: 202607100003
Revises: 202607100002
Create Date: 2026-07-10 00:00:03
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607100003"
down_revision: str | Sequence[str] | None = "202607100002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_idempotency_keys_tenant_owner_key",
        "idempotency_keys",
        ["tenant_id", "owner_user_id", "key"],
        unique=True,
    )
    op.create_index(
        "ix_idempotency_keys_tenant_run",
        "idempotency_keys",
        ["tenant_id", "run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_tenant_run", table_name="idempotency_keys")
    op.drop_index("uq_idempotency_keys_tenant_owner_key", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
