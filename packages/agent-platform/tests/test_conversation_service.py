from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from agent_platform.conversation_service import ConversationService
from agent_platform.conversations import (
    ConversationMessage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from agent_platform.identity import TenantContext


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
        message_metadata: dict[str, Any] | None = None,
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
            message_metadata=message_metadata or {},
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
        message_metadata: dict[str, Any],
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
            message_metadata=message_metadata,
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
        del context
        previous = self.records.get(thread_id)
        state = ConversationState(
            thread_id=thread_id,
            pending_action=action,
            pending_question=question,
            state_data=state_data,
            version=(previous.version + 1) if previous else 1,
            expires_at=expires_at,
            updated_at=datetime.now(UTC),
        )
        self.records[thread_id] = state
        return state

    async def clear_pending(
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
                "pending_action": None,
                "pending_question": None,
                "state_data": {},
                "version": previous.version + 1,
                "expires_at": None,
                "updated_at": datetime.now(UTC),
            }
        )
        self.records[thread_id] = state
        return state


def test_conversation_history_and_state_are_storage_independent() -> None:
    async def scenario() -> None:
        context = TenantContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            timezone="Asia/Shanghai",
            locale="zh-CN",
        )
        service = ConversationService(
            threads=MemoryThreadStore(),
            messages=MemoryMessageStore(),
            states=MemoryStateStore(),
        )
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
            message_metadata={"parts": [{"type": "product_result"}]},
        )
        pending = await service.set_pending(
            context,
            thread_id=thread.id,
            action="choice",
            question="选择哪一项？",
            state_data={"options": ["a", "b"]},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        assert [message.role for message in await service.list_messages(context, thread.id)] == [
            ConversationRole.user,
            ConversationRole.assistant,
        ]
        assert pending.state_data == {"options": ["a", "b"]}
        cleared = await service.clear_pending(context, thread.id)
        assert cleared is not None
        assert cleared.pending_action is None
        assert cleared.version == pending.version + 1

    asyncio.run(scenario())
