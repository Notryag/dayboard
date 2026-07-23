"""Conversation persistence use cases independent of product and storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from agent_platform.conversations import (
    ConversationMessage,
    ConversationMessagePage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from agent_platform.identity import TenantContext


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

    async def set_pending(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        action: str,
        question: str,
        state_data: dict[str, Any],
        expires_at: datetime,
    ) -> ConversationState: ...

    async def clear_pending(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None: ...


class ConversationService:
    def __init__(
        self,
        threads: ConversationThreadStore,
        messages: ConversationMessageStore,
        states: ConversationStateStore,
    ) -> None:
        self.threads = threads
        self.messages = messages
        self.states = states

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
            raise LookupError("Conversation thread not found")
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
            raise LookupError("Conversation thread not found")
        return thread

    async def get_state(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        await self.require_thread(context, thread_id)
        return await self.states.get(context, thread_id)

    async def set_pending(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        action: str,
        question: str,
        state_data: dict[str, Any],
        expires_at: datetime,
    ) -> ConversationState:
        await self.require_thread(context, thread_id)
        return await self.states.set_pending(
            context,
            thread_id=thread_id,
            action=action,
            question=question,
            state_data=state_data,
            expires_at=expires_at,
        )

    async def clear_pending(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        return await self.states.clear_pending(context, thread_id)
