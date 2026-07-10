from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import ConversationMessageRow, ConversationThreadRow
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
