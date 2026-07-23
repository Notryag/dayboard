"""Persisted Run lifecycle independent of a product or storage implementation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from agent_platform.core.events import (
    EventExtensionEnvelope,
    build_run_failure_event_extension,
)
from agent_platform.core.identity import TenantContext
from agent_platform.core.runs import AgentRun, AgentRunEvent, AgentRunEventCategory, AgentRunStatus
from agent_platform.ports.unit_of_work import RunUnitOfWork


class AgentRunService:
    def __init__(self, unit_of_work: RunUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.runs = unit_of_work.runs
        self.events = unit_of_work.events

    async def create_run(
        self,
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> AgentRun:
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
        return run

    async def mark_running(self, context: TenantContext, run: AgentRun) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run.id,
            from_statuses={AgentRunStatus.queued},
            status=AgentRunStatus.running,
        )
        if transitioned is None:
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
        extension: EventExtensionEnvelope | None = None,
        category: AgentRunEventCategory = AgentRunEventCategory.tool,
    ) -> None:
        await self.events.append(
            context,
            run_id=run_id,
            event_type=event_type,
            category=category,
            content=content,
            extension=extension,
        )

    async def mark_completed(
        self,
        context: TenantContext,
        run: AgentRun,
        *,
        result_message: str,
        extension: EventExtensionEnvelope | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run.id,
            from_statuses={AgentRunStatus.running},
            status=AgentRunStatus.completed,
            result_message=result_message,
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_completed",
            category=AgentRunEventCategory.lifecycle,
            content=result_message,
            extension=extension,
        )
        return True

    async def mark_needs_clarification(
        self,
        context: TenantContext,
        run: AgentRun,
        *,
        question: str,
        extension: EventExtensionEnvelope | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run.id,
            from_statuses={AgentRunStatus.running},
            status=AgentRunStatus.needs_clarification,
            result_message=question,
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="clarification_requested",
            category=AgentRunEventCategory.clarification,
            content=question,
            extension=extension,
        )
        return True

    async def mark_failed(
        self,
        context: TenantContext,
        run: AgentRun,
        *,
        error_type: str,
        error_message: str,
        from_statuses: set[AgentRunStatus] | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run.id,
            from_statuses=from_statuses or {AgentRunStatus.queued, AgentRunStatus.running},
            status=AgentRunStatus.failed,
            result_message=error_message,
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_failed",
            category=AgentRunEventCategory.error,
            content=error_message,
            extension=build_run_failure_event_extension(error_type),
        )
        return True

    async def mark_cancelled(
        self,
        context: TenantContext,
        run: AgentRun,
        *,
        event_content: str | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run.id,
            from_statuses={AgentRunStatus.queued, AgentRunStatus.running},
            status=AgentRunStatus.cancelled,
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            run_id=run.id,
            event_type="run_cancelled",
            category=AgentRunEventCategory.lifecycle,
            content=event_content,
        )
        return True

    async def get_run(self, context: TenantContext, run_id: UUID) -> AgentRun | None:
        return await self.runs.get(context, run_id)

    async def get_run_for_update(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> AgentRun | None:
        return await self.runs.get_for_update(context, run_id)

    async def get_run_for_worker(self, run_id: UUID) -> AgentRun | None:
        return await self.runs.get_for_worker(run_id)

    async def get_active_thread_run(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> AgentRun | None:
        return await self.runs.get_active_for_thread(context, thread_id)

    async def list_events(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]:
        return await self.events.list_for_run(context, run_id, after_seq=after_seq)

    async def list_stale_running(self, *, updated_before: datetime) -> list[AgentRun]:
        return await self.runs.list_stale_running(updated_before=updated_before)

    async def list_stale_queued(self, *, created_before: datetime) -> list[AgentRun]:
        return await self.runs.list_stale_queued(created_before=created_before)
