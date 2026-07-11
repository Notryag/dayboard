"""Add voice transcription records.

Revision ID: 202607110002
Revises: 202607110001
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607110002"
down_revision: str | None = "202607110001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=240), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("audio_size_bytes", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(length=12000), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("language", sa.String(length=40), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=240), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_voice_transcripts_tenant_owner_created",
        "voice_transcripts",
        ["tenant_id", "owner_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_transcripts_tenant_owner_created", table_name="voice_transcripts")
    op.drop_table("voice_transcripts")
