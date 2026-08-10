from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from agent_platform.application import ConversationService
from agent_platform.core import (
    AgentRunEvent,
    AgentRunEventCategory,
    ConversationRole,
    ConversationState,
    ConversationThread,
    ConversationThreadStatus,
    InteractionConflictError,
    PendingInteraction,
    PresentationEnvelope,
    EventExtensionEnvelope,
)
from agent_platform.core import UserContext


class MemoryThreadStore:
    def __init__(self) -> None:
        self.records: dict[UUID, ConversationThread] = {}

    async def create(
        self,
        context: UserContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread:
        now = datetime.now(UTC)
        thread = ConversationThread(
            id=thread_id or uuid4(),
            user_id=context.user_id,
            is_primary=False,
            title=title,
            status=ConversationThreadStatus.active,
            summary=None,
            created_at=now,
            updated_at=now,
        )
        self.records[thread.id] = thread
        return thread

    async def get(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        thread = self.records.get(thread_id)
        if thread is None or thread.user_id != context.user_id:
            return None
        return thread

    async def get_or_create_primary(self, context: UserContext) -> ConversationThread:
        existing = next(
            (
                thread
                for thread in self.records.values()
                if thread.user_id == context.user_id
                and thread.is_primary
            ),
            None,
        )
        if existing is not None:
            return existing
        thread = await self.create(context)
        primary = thread.model_copy(update={"is_primary": True})
        self.records[primary.id] = primary
        return primary

    async def update_summary(
        self,
        context: UserContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread | None:
        thread = await self.get(context, thread_id)
        if thread is None:
            return None
        updated = thread.model_copy(update={"summary": summary, "updated_at": datetime.now(UTC)})
        self.records[thread_id] = updated
        return updated


class MemoryRunEventStore:
    def __init__(self) -> None:
        self.records: list[AgentRunEvent] = []

    async def append_message_once(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        extension: EventExtensionEnvelope | None = None,
    ) -> AgentRunEvent:
        del context
        event_type = {
            ConversationRole.user: "message.human",
            ConversationRole.assistant: "message.ai",
        }[role]
        existing = next(
            (
                event
                for event in self.records
                if (event.run_id, event.event_type) == (run_id, event_type)
            ),
            None,
        )
        if existing is not None:
            if role == ConversationRole.assistant:
                updates = {"extension": extension}
                if content:
                    updates["content"] = content
                updated = existing.model_copy(update=updates)
                self.records[self.records.index(existing)] = updated
                return updated
            return existing
        event = AgentRunEvent(
            id=uuid4(),
            thread_id=thread_id,
            run_id=run_id,
            seq=len(self.records) + 1,
            event_type=event_type,
            category=AgentRunEventCategory.message,
            content=content,
            extension=extension,
            created_at=datetime.now(UTC),
        )
        self.records.append(event)
        return event

    async def get_message_for_run(
        self,
        context: UserContext,
        run_id: UUID,
        role: ConversationRole,
    ) -> AgentRunEvent | None:
        del context
        event_type = {
            ConversationRole.user: "message.human",
            ConversationRole.assistant: "message.ai",
        }[role]
        return next(
            (
                event
                for event in self.records
                if event.run_id == run_id and event.event_type == event_type
            ),
            None,
        )

    async def get_execution_input_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRunEvent | None:
        del context, run_id
        return None

    async def list_messages_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> list[AgentRunEvent]:
        del context
        return [event for event in self.records if event.thread_id == thread_id]

    async def list_message_page_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[AgentRunEvent], UUID | None]:
        messages = await self.list_messages_for_thread(context, thread_id)
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
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        del context
        return self.records.get(thread_id)

    async def set_interaction(
        self,
        context: UserContext,
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
        context: UserContext,
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
        context: UserContext,
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
        self.events = MemoryRunEventStore()
        self.states = MemoryStateStore()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_conversation_history_and_state_are_storage_independent() -> None:
    async def scenario() -> None:
        context = UserContext(
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
