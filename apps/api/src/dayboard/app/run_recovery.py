"""Dayboard policy for recovering Runs abandoned by workers or the queue."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from agent_platform.core import UserContext
from agent_platform.application import AgentRunService, ConversationService
from agent_platform.core import AgentRunStatus
from dayboard.app.run_receipts import load_run_receipts, merge_receipt_parts
from dayboard.app.conversation_presentations import (
    build_dayboard_presentation,
    dayboard_presentation_parts,
)


async def recover_stale_running_runs(
    service: AgentRunService,
    *,
    updated_before: datetime,
    timezone: str,
    locale: str,
    conversations: ConversationService,
) -> list[UUID]:
    recovered: list[UUID] = []
    for run in await service.list_stale_running(updated_before=updated_before):
        context = UserContext(
            user_id=run.user_id,
            timezone=timezone,
            locale=locale,
        )
        latest = await service.get_run_for_update(context, run.id)
        if (
            latest is None
            or latest.status != AgentRunStatus.running
            or latest.updated_at >= updated_before
        ):
            continue
        receipts = await load_run_receipts(service.unit_of_work, context, run.id)
        message = (
            "执行已中断，部分操作已完成，请查看结果，仅继续未完成的操作，避免重复提交。"
            if receipts
            else "执行超时，请重试"
        )
        if await service.mark_failed(
            context,
            latest,
            error_type="StaleRunRecovered",
            error_message=message,
            from_statuses={AgentRunStatus.running},
        ):
            existing = await conversations.get_assistant_message_for_run(context, run.id)
            parts = merge_receipt_parts(
                dayboard_presentation_parts(existing.presentation if existing else None),
                receipts,
            )
            await conversations.upsert_assistant_message(
                context,
                thread_id=run.thread_id,
                run_id=run.id,
                content=message,
                presentation=build_dayboard_presentation(parts),
            )
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
        context = UserContext(
            user_id=run.user_id,
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
