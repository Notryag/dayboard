from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import UserContext
from agent_platform.core import (
    ConversationState,
    ConversationThread,
    ConversationThreadStatus,
    PendingInteraction,
)
from dayboard.db.models import (
    ConversationStateRow,
    ConversationThreadRow,
)


def conversation_thread_from_row(row: ConversationThreadRow) -> ConversationThread:
    return ConversationThread(
        id=row.id,
        user_id=row.user_id,
        is_primary=row.is_primary,
        title=row.title,
        status=ConversationThreadStatus(row.status),
        summary=row.summary,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def conversation_state_from_row(row: ConversationStateRow) -> ConversationState:
    interaction = None
    if row.interaction_type is not None:
        if (
            row.interaction_schema_version is None
            or row.interaction_source_run_id is None
            or row.interaction_prompt is None
        ):
            raise RuntimeError("Persisted interaction is incomplete")
        interaction = PendingInteraction(
            interaction_type=row.interaction_type,
            schema_version=row.interaction_schema_version,
            source_run_id=row.interaction_source_run_id,
            prompt=row.interaction_prompt,
            payload=row.interaction_payload,
        )
    return ConversationState(
        thread_id=row.thread_id,
        interaction=interaction,
        version=row.version,
        expires_at=row.expires_at,
        updated_at=row.updated_at,
    )


class ConversationThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: UserContext,
        *,
        thread_id: UUID | None = None,
        title: str | None = None,
    ) -> ConversationThread:
        values = dict(
            user_id=context.user_id,
            title=title,
            status=ConversationThreadStatus.active.value,
            is_primary=False,
        )
        if thread_id is not None:
            values["id"] = thread_id
        row = ConversationThreadRow(**values)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return conversation_thread_from_row(row)

    async def get(self, context: UserContext, thread_id: UUID) -> ConversationThread | None:
        row = await self.session.scalar(
            select(ConversationThreadRow).where(
                ConversationThreadRow.id == thread_id,
                ConversationThreadRow.user_id == context.user_id,
                ConversationThreadRow.deleted_at.is_(None),
            )
        )
        return conversation_thread_from_row(row) if row else None

    async def get_primary(self, context: UserContext) -> ConversationThread | None:
        row = await self.session.scalar(
            select(ConversationThreadRow)
            .where(
                ConversationThreadRow.user_id == context.user_id,
                ConversationThreadRow.is_primary.is_(True),
                ConversationThreadRow.deleted_at.is_(None),
            )
        )
        return conversation_thread_from_row(row) if row else None

    async def get_or_create_primary(self, context: UserContext) -> ConversationThread:
        statement = (
            insert(ConversationThreadRow)
            .values(
                user_id=context.user_id,
                is_primary=True,
                status=ConversationThreadStatus.active.value,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id"],
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
        context: UserContext,
        thread_id: UUID,
        summary: str,
    ) -> ConversationThread | None:
        row = await self.session.scalar(
            update(ConversationThreadRow)
            .where(
                ConversationThreadRow.id == thread_id,
                ConversationThreadRow.user_id == context.user_id,
                ConversationThreadRow.deleted_at.is_(None),
            )
            .values(summary=summary, updated_at=func.now())
            .returning(ConversationThreadRow)
        )
        return conversation_thread_from_row(row) if row else None


class ConversationStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.user_id == context.user_id,
            )
        )
        return conversation_state_from_row(row) if row else None

    async def set_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        interaction: PendingInteraction,
        expires_at: datetime,
    ) -> ConversationState:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.user_id == context.user_id,
            )
        )
        if row is None:
            row = ConversationStateRow(
                thread_id=thread_id,
                user_id=context.user_id,
                interaction_type=interaction.interaction_type,
                interaction_schema_version=interaction.schema_version,
                interaction_source_run_id=interaction.source_run_id,
                interaction_prompt=interaction.prompt,
                interaction_payload=interaction.payload,
                expires_at=expires_at,
            )
            self.session.add(row)
        else:
            row.interaction_type = interaction.interaction_type
            row.interaction_schema_version = interaction.schema_version
            row.interaction_source_run_id = interaction.source_run_id
            row.interaction_prompt = interaction.prompt
            row.interaction_payload = interaction.payload
            row.expires_at = expires_at
            row.version += 1
        await self.session.flush()
        await self.session.refresh(row)
        return conversation_state_from_row(row)

    async def consume_interaction(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        expected_version: int,
        consumed_at: datetime,
    ) -> ConversationState | None:
        row = await self.session.scalar(
            update(ConversationStateRow)
            .where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.user_id == context.user_id,
                ConversationStateRow.version == expected_version,
                ConversationStateRow.interaction_type.is_not(None),
                ConversationStateRow.expires_at > consumed_at,
            )
            .values(
                interaction_type=None,
                interaction_schema_version=None,
                interaction_source_run_id=None,
                interaction_prompt=None,
                interaction_payload={},
                expires_at=None,
                version=ConversationStateRow.version + 1,
                updated_at=func.now(),
            )
            .returning(ConversationStateRow)
            .execution_options(populate_existing=True)
        )
        return conversation_state_from_row(row) if row else None

    async def clear_interaction(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> ConversationState | None:
        row = await self.session.scalar(
            select(ConversationStateRow).where(
                ConversationStateRow.thread_id == thread_id,
                ConversationStateRow.user_id == context.user_id,
            )
        )
        if row is None or row.interaction_type is None:
            return conversation_state_from_row(row) if row else None
        row.interaction_type = None
        row.interaction_schema_version = None
        row.interaction_source_run_id = None
        row.interaction_prompt = None
        row.interaction_payload = {}
        row.expires_at = None
        row.version += 1
        await self.session.flush()
        await self.session.refresh(row)
        return conversation_state_from_row(row)
