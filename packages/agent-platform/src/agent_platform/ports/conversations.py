"""Persistence ports for conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from agent_platform.core.conversations import (
    ConversationState,
    ConversationThread,
)
from agent_platform.core.identity import UserContext
from agent_platform.core.interactions import PendingInteraction


class ConversationThreadStore(Protocol):
    async def create(
        self,
        context: UserContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread: ...

    async def get(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationThread | None: ...

    async def get_or_create_primary(self, context: UserContext) -> ConversationThread: ...

    async def update_summary(
        self,
        context: UserContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread | None: ...


class ConversationStateStore(Protocol):
    async def get(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None: ...

    async def set_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState: ...

    async def consume_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        expected_version: int,
        consumed_at: datetime,
    ) -> ConversationState | None: ...

    async def clear_interaction(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None: ...
