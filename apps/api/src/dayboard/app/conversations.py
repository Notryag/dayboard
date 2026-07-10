from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.conversation_repositories import (
    ConversationMessageRepository,
    ConversationStateRepository,
    ConversationThreadRepository,
)
from dayboard.db.models import ConversationMessageRow, ConversationStateRow, ConversationThreadRow
from dayboard.domain.conversations import (
    ConversationMessage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)


def conversation_thread_from_row(row: ConversationThreadRow) -> ConversationThread:
    return ConversationThread(
        id=row.id,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        status=row.status,
        summary=row.summary,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def conversation_message_from_row(row: ConversationMessageRow) -> ConversationMessage:
    return ConversationMessage(
        id=row.id,
        thread_id=row.thread_id,
        run_id=row.run_id,
        role=ConversationRole(row.role),
        content=row.content,
        message_metadata=row.message_metadata,
        created_at=row.created_at,
    )


def conversation_state_from_row(row: ConversationStateRow) -> ConversationState:
    return ConversationState(
        thread_id=row.thread_id,
        pending_action=row.pending_action,
        pending_question=row.pending_question,
        state_data=row.state_data,
        version=row.version,
        expires_at=row.expires_at,
        updated_at=row.updated_at,
    )


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.threads = ConversationThreadRepository(session)
        self.messages = ConversationMessageRepository(session)
        self.states = ConversationStateRepository(session)

    async def create_thread(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThreadRow:
        return await self.threads.create(context, thread_id=thread_id, title=title)

    async def require_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThreadRow:
        thread = await self.threads.get(context, thread_id)
        if thread is None:
            raise LookupError("Conversation thread not found")
        return thread

    async def get_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationThread | None:
        row = await self.threads.get(context, thread_id)
        return conversation_thread_from_row(row) if row else None

    async def append_message(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        message_metadata: dict | None = None,
    ) -> ConversationMessage:
        row = await self.messages.append_once(
            context,
            thread_id=thread_id,
            run_id=run_id,
            role=role,
            content=content,
            message_metadata=message_metadata,
        )
        return conversation_message_from_row(row)

    async def list_messages(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        await self.require_thread(context, thread_id)
        rows = await self.messages.list_for_thread(context, thread_id)
        return [conversation_message_from_row(row) for row in rows]

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread:
        row = await self.threads.update_summary(context, thread_id, summary)
        if row is None:
            raise LookupError("Conversation thread not found")
        return conversation_thread_from_row(row)

    async def get_state(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        await self.require_thread(context, thread_id)
        row = await self.states.get(context, thread_id)
        return conversation_state_from_row(row) if row else None

    async def set_pending_clarification(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        question: str,
    ) -> ConversationState:
        row = await self.states.set_pending(
            context,
            thread_id=thread_id,
            action="clarification",
            question=question,
            state_data={"source_run_id": str(run_id)},
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        return conversation_state_from_row(row)

    async def clear_pending(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        row = await self.states.clear_pending(context, thread_id)
        return conversation_state_from_row(row) if row else None
