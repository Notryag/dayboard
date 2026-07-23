from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
from agent_platform.core import (
    ConversationMessage,
    ConversationRole,
    ConversationState,
    ConversationThread,
)
from dayboard.db.models import (
    ConversationMessageRow,
    ConversationStateRow,
    ConversationThreadRow,
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


class ConversationThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: TenantContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread:
        values = dict(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            title=title,
            status="isolated",
            is_primary=False,
        )
        if thread_id is not None:
            values["id"] = thread_id
        row = ConversationThreadRow(**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return conversation_thread_from_row(row)

    async def get(self, context: TenantContext, thread_id: UUID) -> ConversationThread | None:
        row = await self.session.scalar(
            select(ConversationThreadRow).where(
                ConversationThreadRow.id == thread_id,
                ConversationThreadRow.tenant_id == context.tenant_id,
                ConversationThreadRow.owner_user_id == context.user_id,
                ConversationThreadRow.deleted_at.is_(None),
            )
        )
        return conversation_thread_from_row(row) if row else None

    async def get_primary(self, context: TenantContext) -> ConversationThread | None:
        row = await self.session.scalar(
            select(ConversationThreadRow)
            .where(
                ConversationThreadRow.tenant_id == context.tenant_id,
                ConversationThreadRow.owner_user_id == context.user_id,
                ConversationThreadRow.is_primary.is_(True),
                ConversationThreadRow.deleted_at.is_(None),
            )
        )
        return conversation_thread_from_row(row) if row else None

    async def get_or_create_primary(self, context: TenantContext) -> ConversationThread:
        statement = (
            insert(ConversationThreadRow)
            .values(
                tenant_id=context.tenant_id,
                owner_user_id=context.user_id,
                is_primary=True,
                status="active",
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "owner_user_id"],
                index_where=(
                    ConversationThreadRow.is_primary.is_(True)
                    & ConversationThreadRow.deleted_at.is_(None)
                ),
            )
            .returning(ConversationThreadRow)
        )
        row = (await self.session.execute(statement)).scalar_one_or_none()
        if row is not None:
            return conversation_thread_from_row(row)
        existing = await self.get_primary(context)
        if existing is None:
            raise RuntimeError("Primary conversation conflict was not persisted")
        return existing

    async def update_summary(
        self,
        context: TenantContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread | None:
        row = await self.session.scalar(
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
        return conversation_thread_from_row(row) if row else None


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
    ) -> ConversationMessage:
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
            return conversation_message_from_row(row)
        existing = await self.session.scalar(
            select(ConversationMessageRow).where(
                ConversationMessageRow.tenant_id == context.tenant_id,
                ConversationMessageRow.run_id == run_id,
                ConversationMessageRow.role == role.value,
            )
        )
        if existing is None:
            raise RuntimeError("Conversation message conflict was not persisted")
        return conversation_message_from_row(existing)

    async def upsert_assistant(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
        message_metadata: dict,
    ) -> ConversationMessage:
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
        row = (await self.session.execute(statement)).scalar_one()
        return conversation_message_from_row(row)

    async def get_assistant_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> ConversationMessage | None:
        row = await self.session.scalar(
            select(ConversationMessageRow).where(
                ConversationMessageRow.tenant_id == context.tenant_id,
                ConversationMessageRow.owner_user_id == context.user_id,
                ConversationMessageRow.run_id == run_id,
                ConversationMessageRow.role == ConversationRole.assistant.value,
            )
        )
        return conversation_message_from_row(row) if row else None

    async def list_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> list[ConversationMessage]:
        result = await self.session.scalars(
            select(ConversationMessageRow)
            .where(
                ConversationMessageRow.tenant_id == context.tenant_id,
                ConversationMessageRow.owner_user_id == context.user_id,
                ConversationMessageRow.thread_id == thread_id,
            )
            .order_by(ConversationMessageRow.created_at.asc(), ConversationMessageRow.id.asc())
        )
        return [conversation_message_from_row(row) for row in result]

    async def list_page_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[ConversationMessage], UUID | None]:
        statement = select(ConversationMessageRow).where(
            ConversationMessageRow.tenant_id == context.tenant_id,
            ConversationMessageRow.owner_user_id == context.user_id,
            ConversationMessageRow.thread_id == thread_id,
        )
        if before is not None:
            cursor = await self.session.scalar(
                select(ConversationMessageRow).where(
                    ConversationMessageRow.id == before,
                    ConversationMessageRow.tenant_id == context.tenant_id,
                    ConversationMessageRow.owner_user_id == context.user_id,
                    ConversationMessageRow.thread_id == thread_id,
                )
            )
            if cursor is None:
                raise LookupError("Conversation message cursor not found")
            statement = statement.where(
                (ConversationMessageRow.created_at < cursor.created_at)
                | (
                    (ConversationMessageRow.created_at == cursor.created_at)
                    & (ConversationMessageRow.id < cursor.id)
                )
            )
        rows = list(
            await self.session.scalars(
                statement.order_by(
                    ConversationMessageRow.created_at.desc(),
                    ConversationMessageRow.id.desc(),
                ).limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        page.reverse()
        return (
            [conversation_message_from_row(row) for row in page],
            page[0].id if has_more else None,
        )


class ConversationStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.tenant_id == context.tenant_id,
                ConversationStateRow.owner_user_id == context.user_id,
            )
        )
        return conversation_state_from_row(row) if row else None

    async def set_pending(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        action: str,
        question: str,
        state_data: dict,
        expires_at: datetime,
    ) -> ConversationState:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.tenant_id == context.tenant_id,
                ConversationStateRow.owner_user_id == context.user_id,
            )
        )
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
        return conversation_state_from_row(row)

    async def clear_pending(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.tenant_id == context.tenant_id,
                ConversationStateRow.owner_user_id == context.user_id,
            )
        )
        if row is None or row.pending_action is None:
            return conversation_state_from_row(row) if row else None
        row.pending_action = None
        row.pending_question = None
        row.state_data = {}
        row.expires_at = None
        row.version += 1
        await self.session.flush()
        await self.session.refresh(row)
        return conversation_state_from_row(row)
