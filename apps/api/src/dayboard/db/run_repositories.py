from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import IdempotencyClaim, IdempotencyRecord, UserContext
from agent_platform.core import ActiveThreadRunError
from agent_platform.core import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventCategory,
    AgentRunStatus,
    ConversationRole,
    EventExtensionEnvelope,
)
from dayboard.db.models import (
    AgentRunEventRow,
    AgentRunRow,
    ConversationThreadRow,
    IdempotencyKeyRow,
)


ACTIVE_THREAD_RUN_CONSTRAINT = "uq_agent_runs_active_thread"


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        constraint_name = getattr(current, "constraint_name", None)
        if constraint_name is not None:
            return str(constraint_name)
        current = current.__cause__ or current.__context__
    return None


def agent_run_from_row(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        id=row.id,
        user_id=row.user_id,
        thread_id=row.thread_id,
        status=AgentRunStatus(row.status),
        model_name=row.model_name,
        error=row.error,
        message_count=row.message_count,
        first_human_message=row.first_human_message,
        last_ai_message=row.last_ai_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def agent_run_event_from_row(row: AgentRunEventRow) -> AgentRunEvent:
    extension = (
        EventExtensionEnvelope(
            kind=row.extension_kind,
            schema_version=row.extension_schema_version,
            payload=row.extension_payload,
        )
        if row.extension_kind is not None and row.extension_schema_version is not None
        else None
    )
    return AgentRunEvent(
        id=row.id,
        thread_id=row.thread_id,
        run_id=row.run_id,
        seq=row.seq,
        event_type=row.event_type,
        category=AgentRunEventCategory(row.category),
        content=row.content,
        extension=extension,
        created_at=row.created_at,
    )


def idempotency_record_from_row(row: IdempotencyKeyRow) -> IdempotencyRecord:
    return IdempotencyRecord(
        id=row.id,
        user_id=row.user_id,
        key=row.key,
        request_hash=row.request_hash,
        run_id=row.run_id,
        created_at=row.created_at,
    )


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        status: AgentRunStatus = AgentRunStatus.queued,
        run_id: UUID | None = None,
        model_name: str | None = None,
        first_human_message: str | None = None,
    ) -> AgentRun:
        row = AgentRunRow(
            id=run_id or uuid4(),
            user_id=context.user_id,
            thread_id=thread_id,
            status=status.value,
            model_name=model_name,
            message_count=1 if first_human_message else 0,
            first_human_message=first_human_message,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError as exc:
            if _integrity_constraint_name(exc) != ACTIVE_THREAD_RUN_CONSTRAINT:
                raise
            raise ActiveThreadRunError(
                "This conversation already has a command in progress"
            ) from exc
        return agent_run_from_row(row)

    async def transition_status(
        self,
        context: UserContext,
        run_id: UUID,
        *,
        from_statuses: set[AgentRunStatus],
        status: AgentRunStatus,
        error: str | None = None,
        message_count: int | None = None,
        first_human_message: str | None = None,
        last_ai_message: str | None = None,
    ) -> AgentRun | None:
        values: dict[str, Any] = {"status": status.value}
        if error is not None:
            values["error"] = error
        if message_count is not None:
            values["message_count"] = message_count
        if first_human_message is not None:
            values["first_human_message"] = first_human_message
        if last_ai_message is not None:
            values["last_ai_message"] = last_ai_message
        now = datetime.now(UTC)
        if status == AgentRunStatus.running:
            values["started_at"] = now
        elif status in {
            AgentRunStatus.completed,
            AgentRunStatus.needs_clarification,
            AgentRunStatus.failed,
            AgentRunStatus.cancelled,
        }:
            values["completed_at"] = now
        result = await self.session.execute(
            update(AgentRunRow)
            .where(
                AgentRunRow.id == run_id,
                AgentRunRow.user_id == context.user_id,
                AgentRunRow.status.in_(status.value for status in from_statuses),
                AgentRunRow.deleted_at.is_(None),
            )
            .values(**values)
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount != 1:
            return None
        row = await self.get(context, run_id)
        if row is None:
            raise RuntimeError("Transitioned Run could not be reloaded")
        return row

    async def get(self, context: UserContext, run_id: UUID) -> AgentRun | None:
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.user_id == context.user_id,
                AgentRunRow.id == run_id,
                AgentRunRow.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        return agent_run_from_row(row) if row else None

    async def get_for_update(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRun | None:
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.user_id == context.user_id,
                AgentRunRow.id == run_id,
                AgentRunRow.deleted_at.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return agent_run_from_row(row) if row else None

    async def get_for_worker(self, run_id: UUID) -> AgentRun | None:
        """Load persisted execution ownership before a worker creates UserContext."""
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.id == run_id,
                AgentRunRow.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        return agent_run_from_row(row) if row else None

    async def get_active_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> AgentRun | None:
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.user_id == context.user_id,
                AgentRunRow.thread_id == thread_id,
                AgentRunRow.status.in_(
                    (AgentRunStatus.queued.value, AgentRunStatus.running.value)
                ),
                AgentRunRow.deleted_at.is_(None),
            )
            .order_by(AgentRunRow.created_at.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return agent_run_from_row(row) if row else None

    async def list_stale_running(self, *, updated_before: datetime) -> list[AgentRun]:
        result = await self.session.scalars(
            select(AgentRunRow).where(
                AgentRunRow.status == AgentRunStatus.running.value,
                AgentRunRow.updated_at < updated_before,
                AgentRunRow.deleted_at.is_(None),
            )
        )
        return [agent_run_from_row(row) for row in result]

    async def list_stale_queued(self, *, created_before: datetime) -> list[AgentRun]:
        result = await self.session.scalars(
            select(AgentRunRow).where(
                AgentRunRow.status == AgentRunStatus.queued.value,
                AgentRunRow.created_at < created_before,
                AgentRunRow.deleted_at.is_(None),
            )
        )
        return [agent_run_from_row(row) for row in result]


class PostgresIdempotencyStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        context: UserContext,
        *,
        key: str,
    ) -> IdempotencyRecord | None:
        row = await self.session.scalar(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.user_id == context.user_id,
                IdempotencyKeyRow.key == key,
            )
        )
        return idempotency_record_from_row(row) if row else None

    async def claim(
        self,
        context: UserContext,
        *,
        key: str,
        request_hash: str,
        run_id: UUID,
    ) -> IdempotencyClaim:
        statement = (
            insert(IdempotencyKeyRow)
            .values(
                user_id=context.user_id,
                key=key,
                request_hash=request_hash,
                run_id=run_id,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "key"],
            )
            .returning(IdempotencyKeyRow)
        )
        created = (await self.session.execute(statement)).scalar_one_or_none()
        if created is not None:
            return IdempotencyClaim(record=idempotency_record_from_row(created), created=True)
        existing = await self.session.scalar(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.user_id == context.user_id,
                IdempotencyKeyRow.key == key,
            )
        )
        if existing is None:
            raise RuntimeError("Idempotency key claim was not persisted")
        return IdempotencyClaim(record=idempotency_record_from_row(existing), created=False)

    async def delete_created_before(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(IdempotencyKeyRow).where(IdempotencyKeyRow.created_at < cutoff)
        )
        return int(result.rowcount or 0)

class AgentRunEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        event_type: str,
        category: AgentRunEventCategory,
        content: str | None = None,
        extension: EventExtensionEnvelope | None = None,
    ) -> AgentRunEvent:
        seq = await self._next_seq(context, thread_id, run_id)
        row = AgentRunEventRow(
            user_id=context.user_id,
            thread_id=thread_id,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            category=category.value,
            content=content,
            extension_kind=extension.kind if extension is not None else None,
            extension_schema_version=(
                extension.schema_version if extension is not None else None
            ),
            extension_payload=extension.payload if extension is not None else {},
        )
        self.session.add(row)
        await self.session.flush()
        return agent_run_event_from_row(row)

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
        event_type = _message_event_type(role)
        existing = await self._get_message_row(context, run_id, event_type)
        if existing is not None:
            if role == ConversationRole.assistant:
                if content:
                    existing.content = content
                if extension is not None:
                    existing.extension_kind = extension.kind
                    existing.extension_schema_version = extension.schema_version
                    existing.extension_payload = extension.payload
                await self.session.flush()
            return agent_run_event_from_row(existing)
        return await self.append(
            context,
            thread_id=thread_id,
            run_id=run_id,
            event_type=event_type,
            category=AgentRunEventCategory.message,
            content=content,
            extension=extension,
        )

    async def append_execution_input_once(
        self,
        context: UserContext,
        *,
        thread_id: UUID,
        run_id: UUID,
        content: str,
    ) -> AgentRunEvent:
        existing = await self._get_event_row(context, run_id, "agent.input")
        if existing is not None:
            return agent_run_event_from_row(existing)
        return await self.append(
            context,
            thread_id=thread_id,
            run_id=run_id,
            event_type="agent.input",
            category=AgentRunEventCategory.model,
            content=content,
        )

    async def list_for_run(
        self,
        context: UserContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]:
        result = await self.session.scalars(
            select(AgentRunEventRow)
            .where(
                AgentRunEventRow.user_id == context.user_id,
                AgentRunEventRow.run_id == run_id,
                AgentRunEventRow.seq > after_seq,
            )
            .order_by(AgentRunEventRow.seq.asc())
        )
        return [agent_run_event_from_row(row) for row in result]

    async def get_message_for_run(
        self,
        context: UserContext,
        run_id: UUID,
        role: ConversationRole,
    ) -> AgentRunEvent | None:
        row = await self._get_message_row(context, run_id, _message_event_type(role))
        return agent_run_event_from_row(row) if row is not None else None

    async def get_execution_input_for_run(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRunEvent | None:
        row = await self._get_event_row(context, run_id, "agent.input")
        return agent_run_event_from_row(row) if row is not None else None

    async def list_messages_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> list[AgentRunEvent]:
        rows = await self.session.scalars(
            select(AgentRunEventRow)
            .where(
                AgentRunEventRow.user_id == context.user_id,
                AgentRunEventRow.thread_id == thread_id,
                AgentRunEventRow.category == AgentRunEventCategory.message.value,
            )
            .order_by(AgentRunEventRow.seq.asc())
        )
        return [agent_run_event_from_row(row) for row in rows]

    async def list_message_page_for_thread(
        self,
        context: UserContext,
        thread_id: UUID,
        *,
        before: UUID | None,
        limit: int,
    ) -> tuple[list[AgentRunEvent], UUID | None]:
        statement = select(AgentRunEventRow).where(
            AgentRunEventRow.user_id == context.user_id,
            AgentRunEventRow.thread_id == thread_id,
            AgentRunEventRow.category == AgentRunEventCategory.message.value,
        )
        if before is not None:
            cursor = await self.session.scalar(
                select(AgentRunEventRow).where(
                    AgentRunEventRow.id == before,
                    AgentRunEventRow.user_id == context.user_id,
                    AgentRunEventRow.thread_id == thread_id,
                    AgentRunEventRow.category == AgentRunEventCategory.message.value,
                )
            )
            if cursor is None:
                raise LookupError("Conversation message cursor not found")
            statement = statement.where(AgentRunEventRow.seq < cursor.seq)
        rows = list(
            await self.session.scalars(
                statement.order_by(AgentRunEventRow.seq.desc()).limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        page.reverse()
        return (
            [agent_run_event_from_row(row) for row in page],
            page[0].id if has_more else None,
        )

    async def _next_seq(self, context: UserContext, thread_id: UUID, run_id: UUID) -> int:
        locked_thread_id = await self.session.scalar(
            select(ConversationThreadRow.id)
            .where(
                ConversationThreadRow.id == thread_id,
                ConversationThreadRow.user_id == context.user_id,
                ConversationThreadRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if locked_thread_id is None:
            raise LookupError("Thread not found while allocating event sequence")
        run_exists = await self.session.scalar(
            select(AgentRunRow.id).where(
                AgentRunRow.id == run_id,
                AgentRunRow.thread_id == thread_id,
                AgentRunRow.user_id == context.user_id,
                AgentRunRow.deleted_at.is_(None),
            )
        )
        if run_exists is None:
            raise LookupError("Run not found while allocating event sequence")
        result = await self.session.scalar(
            select(func.coalesce(func.max(AgentRunEventRow.seq), 0) + 1).where(
                AgentRunEventRow.thread_id == thread_id,
            )
        )
        return int(result)

    async def _get_message_row(
        self,
        context: UserContext,
        run_id: UUID,
        event_type: str,
    ) -> AgentRunEventRow | None:
        return await self._get_event_row(context, run_id, event_type)

    async def _get_event_row(
        self,
        context: UserContext,
        run_id: UUID,
        event_type: str,
    ) -> AgentRunEventRow | None:
        return await self.session.scalar(
            select(AgentRunEventRow).where(
                AgentRunEventRow.user_id == context.user_id,
                AgentRunEventRow.run_id == run_id,
                AgentRunEventRow.event_type == event_type,
            )
        )


def _message_event_type(role: ConversationRole) -> str:
    return {
        ConversationRole.user: "message.human",
        ConversationRole.assistant: "message.ai",
    }[role]
