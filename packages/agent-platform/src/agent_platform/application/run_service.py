"""Persisted Run lifecycle independent of a product or storage implementation."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from agent_platform.core.events import (
    EventExtensionEnvelope,
    build_run_failure_event_extension,
)
from agent_platform.core.identity import UserContext
from agent_platform.core.runs import AgentRun, AgentRunEvent, AgentRunEventCategory, AgentRunStatus
from agent_platform.ports.unit_of_work import RunUnitOfWork


class AgentRunService:
    def __init__(self, unit_of_work: RunUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.runs = unit_of_work.runs
        self.events = unit_of_work.events

    async def create_run(
        self,
        context: UserContext,
        *,
        first_human_message: str,
        thread_id: UUID,
        run_id: UUID | None = None,
        model_name: str | None = None,
    ) -> AgentRun:
        run = await self.runs.create(
            context,
            thread_id=thread_id,
            status=AgentRunStatus.queued,
            run_id=run_id,
            model_name=model_name,
            first_human_message=first_human_message[:2000],
        )
        await self.events.append(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            event_type="run.created",
            category=AgentRunEventCategory.lifecycle,
        )
        return run

    async def mark_running(self, context: UserContext, run: AgentRun) -> bool:
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
            thread_id=run.thread_id,
            run_id=run.id,
            event_type="run.started",
            category=AgentRunEventCategory.lifecycle,
        )
        return True

    async def append_progress(
        self,
        context: UserContext,
        thread_id: UUID,
        run_id: UUID,
        *,
        event_type: str,
        content: str,
        extension: EventExtensionEnvelope | None = None,
        category: AgentRunEventCategory = AgentRunEventCategory.tool,
    ) -> None:
        await self.events.append(
            context,
            thread_id=thread_id,
            run_id=run_id,
            event_type=event_type,
            category=category,
            content=content,
            extension=extension,
        )

    async def mark_completed(
        self,
        context: UserContext,
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
            message_count=run.message_count + 1,
            last_ai_message=result_message[:2000],
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            event_type="run.completed",
            category=AgentRunEventCategory.lifecycle,
            extension=extension,
        )
        return True

    async def mark_needs_clarification(
        self,
        context: UserContext,
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
            message_count=run.message_count + 1,
            last_ai_message=question[:2000],
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            event_type="run.needs_clarification",
            category=AgentRunEventCategory.clarification,
            content=question,
            extension=extension,
        )
        return True

    async def mark_failed(
        self,
        context: UserContext,
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
            error=f"{error_type}: {error_message}"[:4000],
            message_count=run.message_count + 1,
            last_ai_message=error_message[:2000],
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            event_type="run.failed",
            category=AgentRunEventCategory.error,
            content=error_message,
            extension=build_run_failure_event_extension(error_type),
        )
        return True

    async def mark_cancelled(
        self,
        context: UserContext,
        run: AgentRun,
        *,
        event_content: str | None = None,
    ) -> bool:
        transitioned = await self.runs.transition_status(
            context,
            run.id,
            from_statuses={AgentRunStatus.queued, AgentRunStatus.running},
            status=AgentRunStatus.cancelled,
            message_count=run.message_count + (1 if event_content else 0),
            last_ai_message=event_content[:2000] if event_content else None,
        )
        if transitioned is None:
            return False
        await self.events.append(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            event_type="run.cancelled",
            category=AgentRunEventCategory.lifecycle,
            content=event_content,
        )
        return True

    async def get_run(self, context: UserContext, run_id: UUID) -> AgentRun | None:
        return await self.runs.get(context, run_id)

    async def get_run_for_update(
        self,
        context: UserContext,
        run_id: UUID,
    ) -> AgentRun | None:
        return await self.runs.get_for_update(context, run_id)

    async def get_run_for_worker(self, run_id: UUID) -> AgentRun | None:
        return await self.runs.get_for_worker(run_id)

    async def get_active_thread_run(
        self,
        context: UserContext,
        thread_id: UUID,
    ) -> AgentRun | None:
        return await self.runs.get_active_for_thread(context, thread_id)

    async def list_events(
        self,
        context: UserContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]:
        return await self.events.list_for_run(context, run_id, after_seq=after_seq)

    async def list_stale_running(self, *, updated_before: datetime) -> list[AgentRun]:
        return await self.runs.list_stale_running(updated_before=updated_before)

    async def list_stale_queued(self, *, created_before: datetime) -> list[AgentRun]:
        return await self.runs.list_stale_queued(created_before=created_before)
