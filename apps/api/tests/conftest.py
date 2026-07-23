from __future__ import annotations

# ruff: noqa: E402 -- test database safety must be configured before importing dayboard.db

from collections.abc import AsyncIterator
import os
from uuid import UUID

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

os.environ["DAYBOARD_RATE_LIMIT_ENABLED"] = "false"
test_database_url = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://dayboard:dayboard@localhost:5432/dayboard_test",
)
if not (make_url(test_database_url).database or "").endswith("_test"):
    raise RuntimeError("TEST_DATABASE_URL must use a database name ending in _test")
os.environ["DATABASE_URL"] = test_database_url

from dayboard.app.command_schemas import CommandRequest
from dayboard.api.routes import get_command_dispatcher, get_stream_bridge
from dayboard.app.commands import CommandService, get_command_service
from dayboard.app.platform_services import build_run_service
from north.runtime import END_SENTINEL, StreamEvent
from agent_platform.core import TenantContext
from dayboard.api.auth import get_tenant_context
from dayboard.db.models import (
    AgentRunEventRow,
    AgentRunRow,
    CalendarEntryRow,
    ConversationMessageRow,
    ConversationStateRow,
    ConversationThreadRow,
    IdempotencyKeyRow,
    PasswordResetTokenRow,
    ProviderUsageRecordRow,
    TaskItemRow,
    VoiceTranscriptRow,
    ExternalIdentityRow,
    TenantMembershipRow,
    TenantRow,
    UserCredentialRow,
    UserProfileRow,
    UserRow,
    UserSessionRow,
    ReminderDeliveryRow,
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
        run = await build_run_service(self.session).create_run(
            context,
            input_message=request.message,
        )
        await self.session.commit()
        return run.id

    async def create_or_get_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
        *,
        idempotency_key: str | None = None,
        thread_id: UUID | None = None,
    ):
        from agent_platform.core import CommandSubmission

        del idempotency_key
        run = await build_run_service(self.session).create_run(
            context,
            input_message=request.message,
            thread_id=thread_id,
        )
        await self.session.commit()
        return CommandSubmission(run.id, run.status, True, run.thread_id)

    async def fail_command_run(
        self,
        context: TenantContext,
        run_id: UUID,
        exc: Exception,
    ) -> None:
        runs = build_run_service(self.session)
        run = await runs.get_run(context, run_id)
        assert run is not None
        await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        await self.session.commit()


class TestCommandDispatcher:
    def __init__(self) -> None:
        self.started: list[tuple[UUID, TenantContext, CommandRequest]] = []
        self.cancelled: list[UUID] = []

    async def enqueue(self, run_id: UUID, context: TenantContext, request: CommandRequest) -> None:
        self.started.append((run_id, context, request))

    async def cancel(self, run_id: UUID) -> bool:
        self.cancelled.append(run_id)
        return True

    async def health(self) -> dict[str, bool]:
        return {"redis": True, "worker": True}


class TestStreamBridge:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish(
        self,
        run_id: str,
        event_type: str,
        data: dict,
        *,
        namespace: tuple[str, ...] = (),
    ) -> None:
        del namespace
        self.events.append((run_id, event_type, data))

    async def publish_end(self, run_id: str) -> None:
        self.events.append((run_id, "__end__", {}))

    async def subscribe(self, run_id: str, *, last_event_id=None, heartbeat_interval=15):
        del heartbeat_interval
        after_index = int((last_event_id or "0-0").split("-", 1)[0])
        for index, (candidate_run_id, event_type, data) in enumerate(
            self.events, start=1
        ):
            if candidate_run_id != run_id or index <= after_index:
                continue
            if event_type == "__end__":
                yield END_SENTINEL
                return
            yield StreamEvent(
                id=f"{index}-0",
                event=event_type,
                data=data,
            )

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        del run_id, delay


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
        await session.execute(delete(PasswordResetTokenRow))
        await session.execute(delete(UserSessionRow))
        await session.execute(delete(ExternalIdentityRow))
        await session.execute(delete(UserCredentialRow))
        await session.execute(delete(UserProfileRow))
        await session.execute(delete(TenantMembershipRow))
        await session.execute(delete(UserRow))
        await session.execute(delete(TenantRow))
        await session.execute(delete(ReminderDeliveryRow))
        await session.execute(delete(ConversationMessageRow))
        await session.execute(delete(ConversationStateRow))
        await session.execute(delete(ProviderUsageRecordRow))
        await session.execute(delete(AgentRunEventRow))
        await session.execute(delete(IdempotencyKeyRow))
        await session.execute(delete(AgentRunRow))
        await session.execute(delete(ConversationThreadRow))
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.execute(delete(VoiceTranscriptRow))
        await session.commit()
        yield session
        await session.execute(delete(PasswordResetTokenRow))
        await session.execute(delete(UserSessionRow))
        await session.execute(delete(ExternalIdentityRow))
        await session.execute(delete(UserCredentialRow))
        await session.execute(delete(UserProfileRow))
        await session.execute(delete(TenantMembershipRow))
        await session.execute(delete(UserRow))
        await session.execute(delete(TenantRow))
        await session.execute(delete(ReminderDeliveryRow))
        await session.execute(delete(ConversationMessageRow))
        await session.execute(delete(ConversationStateRow))
        await session.execute(delete(ProviderUsageRecordRow))
        await session.execute(delete(AgentRunEventRow))
        await session.execute(delete(IdempotencyKeyRow))
        await session.execute(delete(AgentRunRow))
        await session.execute(delete(ConversationThreadRow))
        await session.execute(delete(CalendarEntryRow))
        await session.execute(delete(TaskItemRow))
        await session.execute(delete(VoiceTranscriptRow))
        await session.commit()


@pytest.fixture
async def api_app(db_session: AsyncSession, tenant_context: TenantContext):
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def override_tenant_context() -> TenantContext:
        return tenant_context

    dispatcher = TestCommandDispatcher()
    stream_bridge = TestStreamBridge()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_tenant_context] = override_tenant_context
    app.dependency_overrides[get_command_service] = lambda: CommandService(db_session)
    app.dependency_overrides[get_command_dispatcher] = lambda: dispatcher
    app.dependency_overrides[get_stream_bridge] = lambda: stream_bridge
    app.state.test_command_dispatcher = dispatcher
    app.state.test_stream_bridge = stream_bridge
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
