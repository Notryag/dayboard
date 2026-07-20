from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import (
    ConversationMessageRow,
    ConversationStateRow,
    ConversationThreadRow,
)
from dayboard.domain.conversations import ConversationRole


class ConversationThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThreadRow:
        values = dict(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            title=title,
            status="active",
        )
        if thread_id is not None:
            values["id"] = thread_id
        row = ConversationThreadRow(**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get(self, context: TenantContext, thread_id: UUID) -> ConversationThreadRow | None:
        return await self.session.scalar(
            select(ConversationThreadRow).where(
                ConversationThreadRow.id == thread_id,
                ConversationThreadRow.tenant_id == context.tenant_id,
                ConversationThreadRow.owner_user_id == context.user_id,
                ConversationThreadRow.deleted_at.is_(None),
            )
        )

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThreadRow | None:
        return await self.session.scalar(
            update(ConversationThreadRow)
            .where(
                ConversationThreadRow.id == thread_id,
                ConversationThreadRow.tenant_id == context.tenant_id,
                ConversationThreadRow.owner_user_id == context.user_id,
                ConversationThreadRow.deleted_at.is_(None),
            )
            .values(summary=summary, updated_at=func.now())
            .returning(ConversationThreadRow)
        )


class ConversationMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append_once(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        role: ConversationRole,
        content: str,
        message_metadata: dict | None = None,
    ) -> ConversationMessageRow:
        statement = (
            insert(ConversationMessageRow)
            .values(
                tenant_id=context.tenant_id,
                owner_user_id=context.user_id,
                thread_id=thread_id,
                run_id=run_id,
                role=role.value,
                content=content,
                message_metadata=message_metadata or {},
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "run_id", "role"],
            )
            .returning(ConversationMessageRow)
        )
        row = (await self.session.execute(statement)).scalar_one_or_none()
        if row is not None:
            return row
        existing = await self.session.scalar(
            select(ConversationMessageRow).where(
                ConversationMessageRow.tenant_id == context.tenant_id,
                ConversationMessageRow.run_id == run_id,
                ConversationMessageRow.role == role.value,
            )
        )
        if existing is None:
            raise RuntimeError("Conversation message conflict was not persisted")
        return existing

    async def upsert_assistant(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        message_metadata: dict,
    ) -> ConversationMessageRow:
        statement = (
            insert(ConversationMessageRow)
            .values(
                tenant_id=context.tenant_id,
                owner_user_id=context.user_id,
                thread_id=thread_id,
                run_id=run_id,
                role=ConversationRole.assistant.value,
                content=content,
                message_metadata=message_metadata,
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "run_id", "role"],
                set_={"content": content, "message_metadata": message_metadata},
            )
            .returning(ConversationMessageRow)
        )
        return (await self.session.execute(statement)).scalar_one()

    async def get_assistant_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> ConversationMessageRow | None:
        return await self.session.scalar(
            select(ConversationMessageRow).where(
                ConversationMessageRow.tenant_id == context.tenant_id,
                ConversationMessageRow.owner_user_id == context.user_id,
                ConversationMessageRow.run_id == run_id,
                ConversationMessageRow.role == ConversationRole.assistant.value,
            )
        )

    async def list_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessageRow]:
        result = await self.session.scalars(
            select(ConversationMessageRow)
            .where(
                ConversationMessageRow.tenant_id == context.tenant_id,
                ConversationMessageRow.owner_user_id == context.user_id,
                ConversationMessageRow.thread_id == thread_id,
            )
            .order_by(ConversationMessageRow.created_at.asc(), ConversationMessageRow.id.asc())
        )
        return list(result)


class ConversationStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationStateRow | None:
        return await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.tenant_id == context.tenant_id,
                ConversationStateRow.owner_user_id == context.user_id,
            )
        )

    async def set_pending(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        action: str,
        question: str,
        state_data: dict,
        expires_at: datetime,
    ) -> ConversationStateRow:
        row = await self.get(context, thread_id)
        if row is None:
            row = ConversationStateRow(
                thread_id=thread_id,
                tenant_id=context.tenant_id,
                owner_user_id=context.user_id,
                pending_action=action,
                pending_question=question,
                state_data=state_data,
                expires_at=expires_at,
            )
            self.session.add(row)
        else:
            row.pending_action = action
            row.pending_question = question
            row.state_data = state_data
            row.expires_at = expires_at
            row.version += 1
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def clear_pending(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationStateRow | None:
        row = await self.get(context, thread_id)
        if row is None or row.pending_action is None:
            return row
        row.pending_action = None
        row.pending_question = None
        row.state_data = {}
        row.expires_at = None
        row.version += 1
        await self.session.flush()
        await self.session.refresh(row)
        return row
