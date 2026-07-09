from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.commands import CommandService
from dayboard.app.runs import AgentRunService
from dayboard.context import TenantContext, get_dev_tenant_context
from dayboard.db.session import get_session
from dayboard.domain.runs import AgentRun, AgentRunEvent

router = APIRouter()


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


@router.post("/api/commands", response_model=CommandResponse)
async def create_command(
    request: CommandRequest,
    session: AsyncSession = Depends(get_session),
    tenant_context: TenantContext = Depends(get_dev_tenant_context),
) -> CommandResponse:
    service = CommandService(session)
    return await service.handle_command(tenant_context, request)


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
