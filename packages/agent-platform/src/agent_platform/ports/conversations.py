"""Persistence ports for conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from agent_platform.core.conversations import (
    ConversationMessage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from agent_platform.core.identity import TenantContext
from agent_platform.core.interactions import PendingInteraction


class ConversationThreadStore(Protocol):
    async def create(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread: ...

    async def get(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThread | None: ...

    async def get_or_create_primary(self, context: TenantContext) -> ConversationThread: ...

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread | None: ...


class ConversationMessageStore(Protocol):
    async def append_once(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        message_metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage: ...

    async def upsert_assistant(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        message_metadata: dict[str, Any],
    ) -> ConversationMessage: ...

    async def get_assistant_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> ConversationMessage | None: ...

    async def list_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]: ...

    async def list_page_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[ConversationMessage], UUID | None]: ...


class ConversationStateStore(Protocol):
    async def get(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None: ...

    async def set_interaction(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState: ...

    async def consume_interaction(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        expected_version: int,
        consumed_at: datetime,
    ) -> ConversationState | None: ...

    async def clear_interaction(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None: ...
