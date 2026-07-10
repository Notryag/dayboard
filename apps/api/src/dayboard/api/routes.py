from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, status
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from dayboard.app.command_dispatcher import RedisCommandDispatcher
from dayboard.app.command_schemas import CommandRequest, CommandRunResponse
from dayboard.app.commands import CommandService, get_command_service
from dayboard.app.runs import AgentRunService
from dayboard.context import TenantContext, get_dev_tenant_context
from dayboard.db.session import get_session
from dayboard.domain.runs import AgentRun, AgentRunEvent

router = APIRouter()

TERMINAL_RUN_EVENTS = {
    "run_completed",
    "run_failed",
    "run_cancelled",
    "clarification_requested",
}
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "needs_clarification"}


def get_command_dispatcher(request: Request) -> RedisCommandDispatcher:
    return request.app.state.command_dispatcher


@router.get("/health")
async def health(
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_dev_tenant_context),
) -> dict[str, str]:
    await session.execute(text("select 1"))
    return {
        "status": "ok",
        "tenant_id": str(tenant_context.tenant_id),
        "user_id": str(tenant_context.user_id),
    }


@router.post(
    "/api/command-runs",
    response_model=CommandRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_command_run(
    request: CommandRequest,
    tenant_context: TenantContext = Depends(get_dev_tenant_context),
    service: CommandService = Depends(get_command_service),
    dispatcher: RedisCommandDispatcher = Depends(get_command_dispatcher),
) -> CommandRunResponse:
    run_id = await service.create_command_run(tenant_context, request)
    try:
        await dispatcher.enqueue(run_id, tenant_context, request)
    except Exception as exc:
        await service.fail_command_run(tenant_context, run_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Command queue unavailable", "run_id": str(run_id)},
        ) from exc
    return CommandRunResponse(run_id=str(run_id))


@router.get("/api/runs/{run_id}", response_model=AgentRun)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_dev_tenant_context),
) -> AgentRun:
    run = await AgentRunService(session).get_run(tenant_context, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/api/runs/{run_id}/events", response_model=list[AgentRunEvent])
async def get_run_events(
    run_id: UUID,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_dev_tenant_context),
) -> list[AgentRunEvent]:
    return await AgentRunService(session).list_events(tenant_context, run_id)


@router.get("/api/runs/{run_id}/events/stream")
async def stream_run_events(
    run_id: UUID,
    request: Request,
    after_seq: int = 0,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_dev_tenant_context),
) -> StreamingResponse:
    service = AgentRunService(session)
    run = await service.get_run(tenant_context, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_stream() -> AsyncIterator[str]:
        cursor = max(after_seq, 0)
        idle_polls = 0
        while not await request.is_disconnected():
            events = await service.list_events(tenant_context, run_id, after_seq=cursor)
            if events:
                idle_polls = 0
                for event in events:
                    cursor = event.seq
                    yield (
                        f"id: {event.seq}\n"
                        f"event: {event.event_type}\n"
                        f"data: {event.model_dump_json()}\n\n"
                    )
                    if event.event_type in TERMINAL_RUN_EVENTS:
                        return
            else:
                if run.status.value in TERMINAL_RUN_STATUSES:
                    return
                idle_polls += 1
                if idle_polls >= 30:
                    yield ": keep-alive\n\n"
                    idle_polls = 0
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
