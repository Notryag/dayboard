from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.encoders import jsonable_encoder

from agent_platform.core import IdempotencyClaim, IdempotencyRecord, TenantContext
from agent_platform.core import ActiveThreadRunError
from agent_platform.core import AgentRun, AgentRunEvent, AgentRunEventCategory, AgentRunStatus
from dayboard.db.models import AgentRunEventRow, AgentRunRow, IdempotencyKeyRow


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
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        thread_id=row.thread_id,
        status=AgentRunStatus(row.status),
        input_message=row.input_message,
        result_message=row.result_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def agent_run_event_from_row(row: AgentRunEventRow) -> AgentRunEvent:
    return AgentRunEvent(
        id=row.id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        seq=row.seq,
        event_type=row.event_type,
        category=AgentRunEventCategory(row.category),
        content=row.content,
        event_metadata=row.event_metadata,
        created_at=row.created_at,
    )


def idempotency_record_from_row(row: IdempotencyKeyRow) -> IdempotencyRecord:
    return IdempotencyRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
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
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None = None,
        status: AgentRunStatus = AgentRunStatus.queued,
        run_id: UUID | None = None,
    ) -> AgentRun:
        row = AgentRunRow(
            id=run_id or uuid4(),
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            thread_id=thread_id or uuid4(),
            status=status.value,
            input_message=input_message,
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
        context: TenantContext,
        run_id: UUID,
        *,
        from_statuses: set[AgentRunStatus],
        status: AgentRunStatus,
        result_message: str | None = None,
    ) -> AgentRun | None:
        values: dict[str, Any] = {"status": status.value}
        if result_message is not None:
            values["result_message"] = result_message
        result = await self.session.execute(
            update(AgentRunRow)
            .where(
                AgentRunRow.id == run_id,
                AgentRunRow.tenant_id == context.tenant_id,
                AgentRunRow.owner_user_id == context.user_id,
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

    async def get(self, context: TenantContext, run_id: UUID) -> AgentRun | None:
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.tenant_id == context.tenant_id,
                AgentRunRow.owner_user_id == context.user_id,
                AgentRunRow.id == run_id,
                AgentRunRow.deleted_at.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        return agent_run_from_row(row) if row else None

    async def get_for_update(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> AgentRun | None:
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.tenant_id == context.tenant_id,
                AgentRunRow.owner_user_id == context.user_id,
                AgentRunRow.id == run_id,
                AgentRunRow.deleted_at.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return agent_run_from_row(row) if row else None

    async def get_for_worker(self, run_id: UUID) -> AgentRun | None:
        """Load persisted execution ownership before a worker creates TenantContext."""
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
        context: TenantContext,
        thread_id: UUID,
    ) -> AgentRun | None:
        row = await self.session.scalar(
            select(AgentRunRow)
            .where(
                AgentRunRow.tenant_id == context.tenant_id,
                AgentRunRow.owner_user_id == context.user_id,
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
        context: TenantContext,
        *,
        key: str,
    ) -> IdempotencyRecord | None:
        row = await self.session.scalar(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.tenant_id == context.tenant_id,
                IdempotencyKeyRow.owner_user_id == context.user_id,
                IdempotencyKeyRow.key == key,
            )
        )
        return idempotency_record_from_row(row) if row else None

    async def claim(
        self,
        context: TenantContext,
        *,
        key: str,
        request_hash: str,
        run_id: UUID,
    ) -> IdempotencyClaim:
        statement = (
            insert(IdempotencyKeyRow)
            .values(
                tenant_id=context.tenant_id,
                owner_user_id=context.user_id,
                key=key,
                request_hash=request_hash,
                run_id=run_id,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "owner_user_id", "key"],
            )
            .returning(IdempotencyKeyRow)
        )
        created = (await self.session.execute(statement)).scalar_one_or_none()
        if created is not None:
            return IdempotencyClaim(record=idempotency_record_from_row(created), created=True)
        existing = await self.session.scalar(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.tenant_id == context.tenant_id,
                IdempotencyKeyRow.owner_user_id == context.user_id,
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
        context: TenantContext,
        *,
        run_id: UUID,
        event_type: str,
        category: AgentRunEventCategory,
        content: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> AgentRunEvent:
        seq = await self._next_seq(context, run_id)
        row = AgentRunEventRow(
            tenant_id=context.tenant_id,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            category=category.value,
            content=content,
            event_metadata=jsonable_encoder(event_metadata or {}),
        )
        self.session.add(row)
        await self.session.flush()
        return agent_run_event_from_row(row)

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]:
        result = await self.session.scalars(
            select(AgentRunEventRow)
            .where(
                AgentRunEventRow.tenant_id == context.tenant_id,
                AgentRunEventRow.run_id == run_id,
                AgentRunEventRow.seq > after_seq,
            )
            .order_by(AgentRunEventRow.seq.asc())
        )
        return [agent_run_event_from_row(row) for row in result]

    async def _next_seq(self, context: TenantContext, run_id: UUID) -> int:
        locked_run_id = await self.session.scalar(
            select(AgentRunRow.id)
            .where(
                AgentRunRow.id == run_id,
                AgentRunRow.tenant_id == context.tenant_id,
                AgentRunRow.owner_user_id == context.user_id,
                AgentRunRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if locked_run_id is None:
            raise LookupError("Run not found while allocating event sequence")
        result = await self.session.scalar(
            select(func.coalesce(func.max(AgentRunEventRow.seq), 0) + 1).where(
                AgentRunEventRow.tenant_id == context.tenant_id,
                AgentRunEventRow.run_id == run_id,
            )
        )
        return int(result)
