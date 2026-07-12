from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from dayboard.context import TenantContext
from dayboard.db.models import AgentRunEventRow, AgentRunRow
from dayboard.db.run_repositories import AgentRunEventRepository, AgentRunRepository
from dayboard.domain.runs import AgentRun, AgentRunEvent, AgentRunEventCategory, AgentRunStatus


ACTIVE_THREAD_RUN_CONSTRAINT = "uq_agent_runs_active_thread"


class ActiveThreadRunError(RuntimeError):
    pass


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


class AgentRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.runs = AgentRunRepository(session)
        self.events = AgentRunEventRepository(session)

    async def create_run(
        self,
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> AgentRunRow:
        try:
            async with self.session.begin_nested():
                run = await self.runs.create(
                    context,
                    input_message=input_message,
                    thread_id=thread_id,
                    status=AgentRunStatus.queued,
                    run_id=run_id,
                )
                await self.events.append(
                    context,
                    run_id=run.id,
                    event_type="run_created",
                    category=AgentRunEventCategory.lifecycle,
                    content=input_message,
                )
        except IntegrityError as exc:
            if _integrity_constraint_name(exc) != ACTIVE_THREAD_RUN_CONSTRAINT:
                raise
            raise ActiveThreadRunError(
                "This conversation already has a command in progress"
            ) from exc
        return run

    async def mark_running(self, context: TenantContext, run: AgentRunRow) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run,
            from_statuses={AgentRunStatus.queued},
            status=AgentRunStatus.running,
        )
        if not transitioned:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_started",
            category=AgentRunEventCategory.lifecycle,
        )
        return True

    async def append_progress(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        event_type: str,
        content: str,
        event_metadata: dict[str, Any] | None = None,
        category: AgentRunEventCategory = AgentRunEventCategory.tool,
    ) -> None:
        await self.events.append(
            context,
            run_id=run_id,
            event_type=event_type,
            category=category,
            content=content,
            event_metadata=event_metadata,
        )

    async def mark_completed(
        self,
        context: TenantContext,
        run: AgentRunRow,
        *,
        result_message: str,
        event_metadata: dict[str, Any] | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run,
            from_statuses={AgentRunStatus.running},
            status=AgentRunStatus.completed,
            result_message=result_message,
        )
        if not transitioned:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_completed",
            category=AgentRunEventCategory.lifecycle,
            content=result_message,
            event_metadata=event_metadata,
        )
        return True

    async def mark_needs_clarification(
        self,
        context: TenantContext,
        run: AgentRunRow,
        *,
        question: str,
        event_metadata: dict[str, Any] | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run,
            from_statuses={AgentRunStatus.running},
            status=AgentRunStatus.needs_clarification,
            result_message=question,
        )
        if not transitioned:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="clarification_requested",
            category=AgentRunEventCategory.clarification,
            content=question,
            event_metadata=event_metadata,
        )
        return True

    async def mark_failed(
        self,
        context: TenantContext,
        run: AgentRunRow,
        *,
        error_type: str,
        error_message: str,
        from_statuses: set[AgentRunStatus] | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run,
            from_statuses=from_statuses
            or {AgentRunStatus.queued, AgentRunStatus.running},
            status=AgentRunStatus.failed,
            result_message=error_message,
        )
        if not transitioned:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_failed",
            category=AgentRunEventCategory.error,
            content=error_message,
            event_metadata={"error_type": error_type},
        )
        return True

    async def mark_cancelled(
        self,
        context: TenantContext,
        run: AgentRunRow,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run,
            from_statuses={AgentRunStatus.queued, AgentRunStatus.running},
            status=AgentRunStatus.cancelled,
        )
        if not transitioned:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_cancelled",
            category=AgentRunEventCategory.lifecycle,
            content="请求已取消",
        )
        return True

    async def get_run(self, context: TenantContext, run_id: UUID) -> AgentRun | None:
        row = await self.runs.get(context, run_id)
        return agent_run_from_row(row) if row else None

    async def get_run_row(self, context: TenantContext, run_id: UUID) -> AgentRunRow | None:
        return await self.runs.get(context, run_id)

    async def get_active_thread_run(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> AgentRun | None:
        row = await self.runs.get_active_for_thread(context, thread_id)
        return agent_run_from_row(row) if row else None

    async def list_events(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]:
        rows = await self.events.list_for_run(context, run_id, after_seq=after_seq)
        return [agent_run_event_from_row(row) for row in rows]

    async def recover_stale_running(
        self,
        *,
        updated_before: datetime,
        timezone: str,
        locale: str,
    ) -> list[UUID]:
        stale_runs = await self.runs.list_stale_running(updated_before=updated_before)
        recovered: list[UUID] = []
        for run in stale_runs:
            context = TenantContext(
                tenant_id=run.tenant_id,
                user_id=run.owner_user_id,
                timezone=timezone,
                locale=locale,
            )
            transitioned = await self.mark_failed(
                context,
                run,
                error_type="StaleRunRecovered",
                error_message="执行超时，请重试",
                from_statuses={AgentRunStatus.running},
            )
            if transitioned:
                recovered.append(run.id)
        return recovered

    async def recover_stale_queued(
        self,
        *,
        created_before: datetime,
        timezone: str,
        locale: str,
    ) -> list[UUID]:
        stale_runs = await self.runs.list_stale_queued(created_before=created_before)
        recovered: list[UUID] = []
        for run in stale_runs:
            context = TenantContext(
                tenant_id=run.tenant_id,
                user_id=run.owner_user_id,
                timezone=timezone,
                locale=locale,
            )
            transitioned = await self.mark_failed(
                context,
                run,
                error_type="QueueWaitTimeout",
                error_message="排队超时，请重试",
                from_statuses={AgentRunStatus.queued},
            )
            if transitioned:
                recovered.append(run.id)
        return recovered
