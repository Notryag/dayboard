from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from agent_platform.core import TenantContext
from agent_platform.application import AgentRunService
from agent_platform.core import AgentRun, AgentRunEvent, AgentRunEventCategory, AgentRunStatus


class MemoryRunStore:
    def __init__(self) -> None:
        self.records: dict[UUID, AgentRun] = {}

    async def create(
        self,
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None,
        status: AgentRunStatus,
        run_id: UUID | None,
    ) -> AgentRun:
        now = datetime.now(UTC)
        run = AgentRun(
            id=run_id or uuid4(),
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            thread_id=thread_id or uuid4(),
            status=status,
            input_message=input_message,
            result_message=None,
            created_at=now,
            updated_at=now,
        )
        self.records[run.id] = run
        return run

    async def transition_status(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        from_statuses: set[AgentRunStatus],
        status: AgentRunStatus,
        result_message: str | None = None,
    ) -> AgentRun | None:
        run = self.records.get(run_id)
        if (
            run is None
            or run.tenant_id != context.tenant_id
            or run.owner_user_id != context.user_id
            or run.status not in from_statuses
        ):
            return None
        updated = run.model_copy(
            update={
                "status": status,
                "result_message": result_message or run.result_message,
                "updated_at": datetime.now(UTC),
            }
        )
        self.records[run_id] = updated
        return updated

    async def get(self, context: TenantContext, run_id: UUID) -> AgentRun | None:
        run = self.records.get(run_id)
        if run is None or (run.tenant_id, run.owner_user_id) != (
            context.tenant_id,
            context.user_id,
        ):
            return None
        return run

    async def get_for_update(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> AgentRun | None:
        return await self.get(context, run_id)

    async def get_for_worker(self, run_id: UUID) -> AgentRun | None:
        return self.records.get(run_id)

    async def get_active_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> AgentRun | None:
        return next(
            (
                run
                for run in self.records.values()
                if run.tenant_id == context.tenant_id
                and run.owner_user_id == context.user_id
                and run.thread_id == thread_id
                and run.status in {AgentRunStatus.queued, AgentRunStatus.running}
            ),
            None,
        )

    async def list_stale_running(self, *, updated_before: datetime) -> list[AgentRun]:
        return [
            run
            for run in self.records.values()
            if run.status == AgentRunStatus.running and run.updated_at < updated_before
        ]

    async def list_stale_queued(self, *, created_before: datetime) -> list[AgentRun]:
        return [
            run
            for run in self.records.values()
            if run.status == AgentRunStatus.queued and run.created_at < created_before
        ]


class MemoryRunEventStore:
    def __init__(self) -> None:
        self.events: list[AgentRunEvent] = []

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
        event = AgentRunEvent(
            id=uuid4(),
            tenant_id=context.tenant_id,
            run_id=run_id,
            seq=len(self.events) + 1,
            event_type=event_type,
            category=category,
            content=content,
            event_metadata=event_metadata or {},
            created_at=datetime.now(UTC),
        )
        self.events.append(event)
        return event

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]:
        return [
            event
            for event in self.events
            if event.tenant_id == context.tenant_id
            and event.run_id == run_id
            and event.seq > after_seq
        ]


class MemoryRunUnitOfWork:
    def __init__(self) -> None:
        self.runs = MemoryRunStore()
        self.events = MemoryRunEventStore()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def test_run_lifecycle_is_storage_independent() -> None:
    async def scenario() -> None:
        context = TenantContext(
            tenant_id=uuid4(),
            user_id=uuid4(),
            timezone="Asia/Shanghai",
            locale="zh-CN",
        )
        unit_of_work = MemoryRunUnitOfWork()
        service = AgentRunService(unit_of_work)

        run = await service.create_run(context, input_message="记录今天的饮食")
        assert await service.mark_running(context, run)
        assert await service.mark_completed(context, run, result_message="已记录")

        completed = await service.get_run(context, run.id)
        assert completed is not None
        assert completed.status == AgentRunStatus.completed
        assert completed.result_message == "已记录"
        assert [event.event_type for event in await service.list_events(context, run.id)] == [
            "run_created",
            "run_started",
            "run_completed",
        ]

    asyncio.run(scenario())
