from __future__ import annotations

from collections.abc import AsyncIterator
import os
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

os.environ["DAYBOARD_RATE_LIMIT_ENABLED"] = "false"

from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.commands import get_command_service
from dayboard.app.runs import AgentRunService
from dayboard.context import TenantContext, get_dev_tenant_context
from dayboard.db.models import AgentRunEventRow, AgentRunRow, CalendarEntryRow, TaskItemRow
from dayboard.db.session import SessionLocal, get_session
from dayboard.main import app
from dayboard.tools import create_calendar_entry, create_task_item


class TestCommandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def handle_command(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        session = self.session
        runs = AgentRunService(session)
        run = await runs.create_run(context, input_message=request.message)
        await runs.mark_running(context, run)

        if request.intent == "calendar_entry" and request.calendar_entry is not None:
            result = await create_calendar_entry(session, context, request.calendar_entry, created_by_run_id=run.id)
            await runs.mark_completed(context, run, result_message=result.summary)
            await session.commit()
            return CommandResponse(run_id=str(run.id), status="completed", message=result.summary, result=result)

        if request.intent == "task_item" and request.task_item is not None:
            result = await create_task_item(session, context, request.task_item, created_by_run_id=run.id)
            await runs.mark_completed(context, run, result_message=result.summary)
            await session.commit()
            return CommandResponse(run_id=str(run.id), status="completed", message=result.summary, result=result)

        question = "几点开始？"
        await runs.mark_needs_clarification(context, run, question=question)
        await session.commit()
        return CommandResponse(
            run_id=str(run.id),
            status="needs_clarification",
            message="More scheduling details are needed.",
            clarification_question=question,
        )


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
        await session.execute(delete(AgentRunEventRow))
        await session.execute(delete(AgentRunRow))
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.commit()
        yield session
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

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_dev_tenant_context] = override_tenant_context
    app.dependency_overrides[get_command_service] = lambda: TestCommandService(db_session)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
