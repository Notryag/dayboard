"""Conversation persistence use cases independent of product and storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from agent_platform.core.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from agent_platform.core.errors import ConversationNotFoundError, InteractionConflictError
from agent_platform.core.identity import TenantContext
from agent_platform.core.interactions import PendingInteraction
from agent_platform.ports.unit_of_work import ConversationUnitOfWork


class ConversationService:
    def __init__(self, unit_of_work: ConversationUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.threads = unit_of_work.threads
        self.messages = unit_of_work.messages
        self.states = unit_of_work.states

    async def create_thread(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread:
        return await self.threads.create(context, thread_id=thread_id, title=title)

    async def require_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThread:
        thread = await self.threads.get(context, thread_id)
        if thread is None:
            raise ConversationNotFoundError("Conversation thread not found")
        return thread

    async def get_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        return await self.threads.get(context, thread_id)

    async def get_or_create_primary_thread(self, context: TenantContext) -> ConversationThread:
        return await self.threads.get_or_create_primary(context)

    async def append_message(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        message_metadata: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        return await self.messages.append_once(
            context,
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )

    async def list_messages(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        await self.require_thread(context, thread_id)
        return await self.messages.list_for_thread(context, thread_id)

    async def list_message_page(
        self,
        context: TenantContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> ConversationMessagePage:
        await self.require_thread(context, thread_id)
        items, next_cursor = await self.messages.list_page_for_thread(
            context,
            thread_id,
            before=before,
            limit=limit,
        )
        return ConversationMessagePage(items=items, next_cursor=next_cursor)

    async def upsert_assistant_message(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        message_metadata: dict[str, Any],
    ) -> ConversationMessage:
        return await self.messages.upsert_assistant(
            context,
            thread_id=thread_id,
            run_id=run_id,
            content=content,
            message_metadata=message_metadata,
        )

    async def get_assistant_message_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> ConversationMessage | None:
        return await self.messages.get_assistant_for_run(context, run_id)

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread:
        thread = await self.threads.update_summary(context, thread_id, summary)
        if thread is None:
            raise ConversationNotFoundError("Conversation thread not found")
        return thread

    async def get_state(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        await self.require_thread(context, thread_id)
        return await self.states.get(context, thread_id)

    async def set_interaction(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState:
        await self.require_thread(context, thread_id)
        return await self.states.set_interaction(
            context,
            thread_id=thread_id,
            interaction=interaction,
            expires_at=expires_at,
        )

    async def consume_interaction(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        expected_version: int,
    ) -> ConversationState:
        state = await self.states.consume_interaction(
            context,
            thread_id=thread_id,
            expected_version=expected_version,
            consumed_at=datetime.now(UTC),
        )
        if state is None:
            raise InteractionConflictError(
                "Interaction is missing, expired, or changed; refresh and try again"
            )
        return state

    async def clear_interaction(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        return await self.states.clear_interaction(context, thread_id)
