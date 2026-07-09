from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.commands import CommandRequest, CommandResponse, CommandService
from dayboard.context import TenantContext, get_dev_tenant_context
from dayboard.db.session import get_session

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
