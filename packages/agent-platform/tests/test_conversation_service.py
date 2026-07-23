from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from agent_platform.application import ConversationService
from agent_platform.core import (
    ConversationMessage,
    ConversationRole,
    ConversationState,
    ConversationThread,
    InteractionConflictError,
    PendingInteraction,
    PresentationEnvelope,
)
from agent_platform.core import TenantContext


class MemoryThreadStore:
    def __init__(self) -> None:
        self.records: dict[UUID, ConversationThread] = {}

    async def create(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread:
        now = datetime.now(UTC)
        thread = ConversationThread(
            id=thread_id or uuid4(),
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            title=title,
            status="active",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        self.records[thread.id] = thread
        return thread

    async def get(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        thread = self.records.get(thread_id)
        if thread is None or (thread.tenant_id, thread.owner_user_id) != (
            context.tenant_id,
            context.user_id,
        ):
            return None
        return thread

    async def get_or_create_primary(self, context: TenantContext) -> ConversationThread:
        existing = next(
            (
                thread
                for thread in self.records.values()
                if thread.tenant_id == context.tenant_id
                and thread.owner_user_id == context.user_id
                and thread.status == "primary"
            ),
            None,
        )
        if existing is not None:
            return existing
        thread = await self.create(context)
        primary = thread.model_copy(update={"status": "primary"})
        self.records[primary.id] = primary
        return primary

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread | None:
        thread = await self.get(context, thread_id)
        if thread is None:
            return None
        updated = thread.model_copy(update={"summary": summary, "updated_at": datetime.now(UTC)})
        self.records[thread_id] = updated
        return updated


class MemoryMessageStore:
    def __init__(self) -> None:
        self.records: list[ConversationMessage] = []

    async def append_once(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        presentation: PresentationEnvelope | None = None,
    ) -> ConversationMessage:
        del context
        existing = next(
            (message for message in self.records if (message.run_id, message.role) == (run_id, role)),
            None,
        )
        if existing is not None:
            return existing
        message = ConversationMessage(
            id=uuid4(),
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            content=content,
            presentation=presentation,
            created_at=datetime.now(UTC),
        )
        self.records.append(message)
        return message

    async def upsert_assistant(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        presentation: PresentationEnvelope | None,
    ) -> ConversationMessage:
        self.records = [
            message
            for message in self.records
            if (message.run_id, message.role) != (run_id, ConversationRole.assistant)
        ]
        return await self.append_once(
            context,
            thread_id=thread_id,
            run_id=run_id,
            role=ConversationRole.assistant,
            content=content,
            presentation=presentation,
        )

    async def get_assistant_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> ConversationMessage | None:
        del context
        return next(
            (
                message
                for message in self.records
                if message.run_id == run_id and message.role == ConversationRole.assistant
            ),
            None,
        )

    async def list_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        del context
        return [message for message in self.records if message.thread_id == thread_id]

    async def list_page_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[ConversationMessage], UUID | None]:
        messages = await self.list_for_thread(context, thread_id)
        if before is not None:
            cursor = next(index for index, item in enumerate(messages) if item.id == before)
            messages = messages[:cursor]
        page = messages[-limit:]
        next_cursor = page[0].id if len(messages) > len(page) else None
        return page, next_cursor


class MemoryStateStore:
    def __init__(self) -> None:
        self.records: dict[UUID, ConversationState] = {}

    async def get(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        del context
        return self.records.get(thread_id)

    async def set_interaction(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState:
        del context
        previous = self.records.get(thread_id)
        state = ConversationState(
            thread_id=thread_id,
            interaction=interaction,
            version=(previous.version + 1) if previous else 1,
            expires_at=expires_at,
            updated_at=datetime.now(UTC),
        )
        self.records[thread_id] = state
        return state

    async def consume_interaction(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        expected_version: int,
        consumed_at: datetime,
    ) -> ConversationState | None:
        del context
        previous = self.records.get(thread_id)
        if (
            previous is None
            or previous.interaction is None
            or previous.version != expected_version
            or (previous.expires_at is not None and previous.expires_at <= consumed_at)
        ):
            return None
        state = previous.model_copy(
            update={
                "interaction": None,
                "version": previous.version + 1,
                "expires_at": None,
                "updated_at": consumed_at,
            }
        )
        self.records[thread_id] = state
        return state

    async def clear_interaction(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        del context
        previous = self.records.get(thread_id)
        if previous is None:
            return None
        state = previous.model_copy(
            update={
                "interaction": None,
                "version": previous.version + 1,
                "expires_at": None,
                "updated_at": datetime.now(UTC),
            }
        )
        self.records[thread_id] = state
        return state


class MemoryConversationUnitOfWork:
    def __init__(self) -> None:
        self.threads = MemoryThreadStore()
        self.messages = MemoryMessageStore()
        self.states = MemoryStateStore()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_conversation_history_and_state_are_storage_independent() -> None:
    async def scenario() -> None:
        context = TenantContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            timezone="Asia/Shanghai",
            locale="zh-CN",
        )
        service = ConversationService(MemoryConversationUnitOfWork())
        thread = await service.create_thread(context, title="记录")
        run_id = uuid4()
        await service.append_message(
            context,
            thread_id=thread.id,
            run_id=run_id,
            role=ConversationRole.user,
            content="记录今天的数据",
        )
        await service.upsert_assistant_message(
            context,
            thread_id=thread.id,
            run_id=run_id,
            content="已记录",
            presentation=PresentationEnvelope(
                kind="example.product-results",
                schema_version=1,
                payload={"parts": [{"type": "product_result"}]},
            ),
        )
        interaction = PendingInteraction(
            interaction_type="example.choice",
            schema_version=1,
            source_run_id=run_id,
            prompt="选择哪一项？",
            payload={"options": ["a", "b"]},
        )
        pending = await service.set_interaction(
            context,
            thread_id=thread.id,
            interaction=interaction,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        assert [message.role for message in await service.list_messages(context, thread.id)] == [
            ConversationRole.user,
            ConversationRole.assistant,
        ]
        assert pending.interaction == interaction
        consumed = await service.consume_interaction(
            context,
            thread_id=thread.id,
            expected_version=pending.version,
        )
        assert consumed.interaction is None
        assert consumed.version == pending.version + 1
        with pytest.raises(InteractionConflictError):
            await service.consume_interaction(
                context,
                thread_id=thread.id,
                expected_version=pending.version,
            )

    asyncio.run(scenario())
