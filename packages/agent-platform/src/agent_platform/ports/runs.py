"""Persistence ports for durable Runs and their events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from agent_platform.core.identity import TenantContext
from agent_platform.core.runs import (
    AgentRun,
    AgentRunEvent,
    AgentRunEventCategory,
    AgentRunStatus,
)


class RunStore(Protocol):
    async def create(
        self,
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None,
        status: AgentRunStatus,
        run_id: UUID | None,
    ) -> AgentRun: ...

    async def transition_status(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        from_statuses: set[AgentRunStatus],
        status: AgentRunStatus,
        result_message: str | None = None,
    ) -> AgentRun | None: ...

    async def get(self, context: TenantContext, run_id: UUID) -> AgentRun | None: ...

    async def get_for_update(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> AgentRun | None: ...

    async def get_for_worker(self, run_id: UUID) -> AgentRun | None: ...

    async def get_active_for_thread(
        self,
        context: TenantContext,
        thread_id: UUID,
    ) -> AgentRun | None: ...

    async def list_stale_running(self, *, updated_before: datetime) -> list[AgentRun]: ...

    async def list_stale_queued(self, *, created_before: datetime) -> list[AgentRun]: ...


class RunEventStore(Protocol):
    async def append(
        self,
        context: TenantContext,
        *,
        run_id: UUID,
        event_type: str,
        category: AgentRunEventCategory,
        content: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> AgentRunEvent: ...

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
        *,
        after_seq: int = 0,
    ) -> list[AgentRunEvent]: ...
