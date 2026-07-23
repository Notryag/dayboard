from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantRow(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class UserRow(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserCredentialRow(TimestampMixin, Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)


class ExternalIdentityRow(TimestampMixin, Base):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_external_identity_subject"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    issuer: Mapped[str] = mapped_column(String(160), nullable=False)
    subject: Mapped[str] = mapped_column(String(320), nullable=False)


class TenantMembershipRow(TimestampMixin, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="owner")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class UserProfileRow(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)


class UserSessionRow(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_token_hash", "token_hash", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PasswordResetTokenRow(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_token_hash", "token_hash", unique=True),
        Index(
            "uq_password_reset_tokens_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("used_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReminderDeliveryRow(TimestampMixin, Base):
    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        Index(
            "uq_reminder_deliveries_active_source_channel",
            "tenant_id",
            "source_type",
            "source_id",
            "channel",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing') AND deleted_at IS NULL"),
        ),
        Index(
            "ix_reminder_deliveries_due",
            "status",
            "next_attempt_at",
            "scheduled_for",
        ),
        Index(
            "ix_reminder_deliveries_tenant_owner_created",
            "tenant_id",
            "owner_user_id",
            "created_at",
        ),
        Index(
            "ix_reminder_deliveries_tenant_owner_unread",
            "tenant_id",
            "owner_user_id",
            "read_at",
            postgresql_where=text("status = 'delivered' AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="in_app")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class CalendarEntryRow(TimestampMixin, Base):
    __tablename__ = "calendar_entries"
    __table_args__ = (
        Index("ix_calendar_entries_tenant_owner_start", "tenant_id", "owner_user_id", "start_time"),
        Index("ix_calendar_entries_tenant_start", "tenant_id", "start_time"),
        Index("ix_calendar_entries_tenant_owner_date", "tenant_id", "owner_user_id", "scheduled_date"),
        CheckConstraint(
            "(timing_kind = 'timed' AND scheduled_date IS NULL AND start_time IS NOT NULL) OR "
            "(timing_kind = 'anytime' AND scheduled_date IS NOT NULL AND start_time IS NULL "
            "AND end_time IS NULL AND reminder IS NULL)",
            name="ck_calendar_entries_timing_shape",
        ),
        Index("ix_calendar_entries_tenant_created_by_run", "tenant_id", "created_by_run_id"),
        Index("ix_calendar_entries_tenant_cancelled_by_run", "tenant_id", "cancelled_by_run_id"),
        Index(
            "uq_calendar_entries_tenant_run_create_operation",
            "tenant_id",
            "created_by_run_id",
            "created_operation_key",
            unique=True,
            postgresql_where=text(
                "created_by_run_id IS NOT NULL AND created_operation_key IS NOT NULL"
            ),
        ),
        Index(
            "uq_calendar_entries_tenant_run_update_operation",
            "tenant_id",
            "updated_by_run_id",
            "updated_operation_key",
            unique=True,
            postgresql_where=text(
                "updated_by_run_id IS NOT NULL AND updated_operation_key IS NOT NULL"
            ),
        ),
        Index(
            "uq_calendar_entries_tenant_run_cancel_operation",
            "tenant_id",
            "cancelled_by_run_id",
            "cancelled_operation_key",
            unique=True,
            postgresql_where=text(
                "cancelled_by_run_id IS NOT NULL AND cancelled_operation_key IS NOT NULL"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    row_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    timing_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="timed")
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    participants: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    reminder: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_operation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_operation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancelled_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancelled_operation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskItemRow(TimestampMixin, Base):
    __tablename__ = "task_items"
    __table_args__ = (
        Index(
            "ix_task_items_tenant_owner_status_due",
            "tenant_id",
            "owner_user_id",
            "status",
            "due_at",
        ),
        Index(
            "uq_task_items_tenant_run_create_operation",
            "tenant_id",
            "created_by_run_id",
            "created_operation_key",
            unique=True,
            postgresql_where=text(
                "created_by_run_id IS NOT NULL AND created_operation_key IS NOT NULL"
            ),
        ),
        Index(
            "uq_task_items_tenant_run_update_operation",
            "tenant_id",
            "updated_by_run_id",
            "updated_operation_key",
            unique=True,
            postgresql_where=text(
                "updated_by_run_id IS NOT NULL AND updated_operation_key IS NOT NULL"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    row_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    reminder: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    created_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_operation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_operation_key: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AgentRunRow(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_tenant_thread_created", "tenant_id", "thread_id", "created_at"),
        Index("ix_agent_runs_tenant_owner_created", "tenant_id", "owner_user_id", "created_at"),
        Index(
            "uq_agent_runs_active_thread",
            "tenant_id",
            "thread_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    input_message: Mapped[str] = mapped_column(String(4000), nullable=False)
    result_message: Mapped[str | None] = mapped_column(String(4000), nullable=True)


class ConversationThreadRow(TimestampMixin, Base):
    __tablename__ = "conversation_threads"
    __table_args__ = (
        Index(
            "ix_conversation_threads_tenant_owner_updated",
            "tenant_id",
            "owner_user_id",
            "updated_at",
        ),
        Index(
            "uq_conversation_threads_primary_owner",
            "tenant_id",
            "owner_user_id",
            unique=True,
            postgresql_where=text("is_primary IS TRUE AND deleted_at IS NULL"),
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_conversation_thread_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    summary: Mapped[str | None] = mapped_column(String(8000), nullable=True)
    summary_through_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class ConversationMessageRow(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index(
            "ix_conversation_messages_tenant_thread_created", "tenant_id", "thread_id", "created_at"
        ),
        Index(
            "uq_conversation_messages_tenant_run_role",
            "tenant_id",
            "run_id",
            "role",
            unique=True,
        ),
        CheckConstraint(
            "presentation_schema_version IS NULL OR presentation_schema_version >= 1",
            name="ck_conversation_message_presentation_schema_version",
        ),
        CheckConstraint(
            "(presentation_kind IS NULL AND presentation_schema_version IS NULL "
            "AND presentation_payload = '{}'::jsonb) OR "
            "(presentation_kind IS NOT NULL AND presentation_schema_version IS NOT NULL)",
            name="ck_conversation_message_presentation_complete",
        ),
        CheckConstraint(
            "presentation_kind IS NULL OR role = 'assistant'",
            name="ck_conversation_message_presentation_assistant_only",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    presentation_kind: Mapped[str | None] = mapped_column(String(80), nullable=True)
    presentation_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    presentation_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ConversationStateRow(Base):
    __tablename__ = "conversation_states"
    __table_args__ = (
        CheckConstraint(
            "interaction_schema_version IS NULL OR interaction_schema_version >= 1",
            name="ck_conversation_state_interaction_schema_version",
        ),
        CheckConstraint(
            "(interaction_type IS NULL AND interaction_schema_version IS NULL "
            "AND interaction_source_run_id IS NULL AND interaction_prompt IS NULL "
            "AND interaction_payload = '{}'::jsonb AND expires_at IS NULL) OR "
            "(interaction_type IS NOT NULL AND interaction_schema_version IS NOT NULL "
            "AND interaction_source_run_id IS NOT NULL AND interaction_prompt IS NOT NULL "
            "AND expires_at IS NOT NULL)",
            name="ck_conversation_state_interaction_complete",
        ),
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    interaction_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    interaction_schema_version: Mapped[int | None] = mapped_column(nullable=True)
    interaction_source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    interaction_prompt: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    interaction_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class VoiceTranscriptRow(Base):
    __tablename__ = "voice_transcripts"
    __table_args__ = (
        Index(
            "ix_voice_transcripts_tenant_owner_created", "tenant_id", "owner_user_id", "created_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    filename: Mapped[str | None] = mapped_column(String(240), nullable=True)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    audio_size_bytes: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str | None] = mapped_column(String(12000), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AgentRunEventRow(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        Index("ix_agent_run_events_tenant_run_seq", "tenant_id", "run_id", "seq", unique=True),
        Index("ix_agent_run_events_tenant_run_created", "tenant_id", "run_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        Index(
            "uq_idempotency_keys_tenant_owner_key",
            "tenant_id",
            "owner_user_id",
            "key",
            unique=True,
        ),
        Index("ix_idempotency_keys_tenant_run", "tenant_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProviderUsageRecordRow(Base):
    __tablename__ = "provider_usage_records"
    __table_args__ = (
        Index("ix_provider_usage_tenant_user_created", "tenant_id", "owner_user_id", "created_at"),
        Index("uq_provider_usage_tenant_run", "tenant_id", "run_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(240), nullable=False)
    input_tokens: Mapped[int] = mapped_column(nullable=False)
    output_tokens: Mapped[int] = mapped_column(nullable=False)
    total_tokens: Mapped[int] = mapped_column(nullable=False)
    usage_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
