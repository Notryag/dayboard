"""Dayboard policy for recovering Runs abandoned by workers or the queue."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from agent_platform.core import TenantContext
from agent_platform.application import AgentRunService
from agent_platform.core import AgentRunStatus


async def recover_stale_running_runs(
    service: AgentRunService,
    *,
    updated_before: datetime,
    timezone: str,
    locale: str,
) -> list[UUID]:
    recovered: list[UUID] = []
    for run in await service.list_stale_running(updated_before=updated_before):
        context = TenantContext(
            tenant_id=run.tenant_id,
            user_id=run.owner_user_id,
            timezone=timezone,
            locale=locale,
        )
        if await service.mark_failed(
            context,
            run,
            error_type="StaleRunRecovered",
            error_message="执行超时，请重试",
            from_statuses={AgentRunStatus.running},
        ):
            recovered.append(run.id)
    return recovered


async def recover_stale_queued_runs(
    service: AgentRunService,
    *,
    created_before: datetime,
    timezone: str,
    locale: str,
) -> list[UUID]:
    recovered: list[UUID] = []
    for run in await service.list_stale_queued(created_before=created_before):
        context = TenantContext(
            tenant_id=run.tenant_id,
            user_id=run.owner_user_id,
            timezone=timezone,
            locale=locale,
        )
        if await service.mark_failed(
            context,
            run,
            error_type="QueueWaitTimeout",
            error_message="排队超时，请重试",
            from_statuses={AgentRunStatus.queued},
        ):
            recovered.append(run.id)
    return recovered
