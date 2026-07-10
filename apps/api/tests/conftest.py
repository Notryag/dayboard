from __future__ import annotations

from collections.abc import AsyncIterator
import os
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

os.environ["DAYBOARD_RATE_LIMIT_ENABLED"] = "false"

from dayboard.app.command_schemas import CommandRequest
from dayboard.api.routes import get_command_dispatcher
from dayboard.app.commands import get_command_service
from dayboard.app.runs import AgentRunService
from dayboard.context import TenantContext, get_dev_tenant_context
from dayboard.db.models import (
    AgentRunEventRow,
    AgentRunRow,
    CalendarEntryRow,
    ProviderUsageRecordRow,
    TaskItemRow,
)
from dayboard.db.session import SessionLocal, get_session
from dayboard.main import app


class TestCommandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> UUID:
        run = await AgentRunService(self.session).create_run(
            context,
            input_message=request.message,
        )
        await self.session.commit()
        return run.id


class TestCommandDispatcher:
    def __init__(self) -> None:
        self.started: list[tuple[UUID, TenantContext, CommandRequest]] = []

    def start(self, run_id: UUID, context: TenantContext, request: CommandRequest) -> None:
        self.started.append((run_id, context, request))


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        await session.execute(delete(ProviderUsageRecordRow))
        await session.execute(delete(AgentRunEventRow))
        await session.execute(delete(AgentRunRow))
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.commit()
        yield session
        await session.execute(delete(ProviderUsageRecordRow))
        await session.execute(delete(AgentRunEventRow))
        await session.execute(delete(AgentRunRow))
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.commit()


@pytest.fixture
async def api_app(db_session: AsyncSession, tenant_context: TenantContext):
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def override_tenant_context() -> TenantContext:
        return tenant_context

    dispatcher = TestCommandDispatcher()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_dev_tenant_context] = override_tenant_context
    app.dependency_overrides[get_command_service] = lambda: TestCommandService(db_session)
    app.dependency_overrides[get_command_dispatcher] = lambda: dispatcher
    app.state.test_command_dispatcher = dispatcher
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
