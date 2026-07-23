from __future__ import annotations

import asyncio
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from north import RuntimeEvent
import pytest
from fake_runtime import fake_executor_factory
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import Settings
from agent_platform.identity import TenantContext
from dayboard.db.provider_usage_repository import ProviderUsageRepository


async def test_command_service_records_provider_usage(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async def fake_invoker(**kwargs):
        sink = kwargs["event_sink"]
        await sink(
            RuntimeEvent(
                "model.completed",
                "model",
                metadata={
                    "call_id": "call-1",
                    "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
                },
            )
        )
        await sink(
            RuntimeEvent(
                "model.completed",
                "model",
                metadata={
                    "call_id": "call-2",
                    "usage": {"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
                },
            )
        )
        return {
            "messages": [
                HumanMessage(content="安排会议"),
                AIMessage(
                    content="调用工具",
                    usage_metadata={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
                ),
                AIMessage(
                    content="会议已创建",
                    usage_metadata={"input_tokens": 30, "output_tokens": 8, "total_tokens": 38},
                ),
            ]
        }

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
    )

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)
    records = await ProviderUsageRepository(db_session).list_for_run(
        tenant_context,
        run_id,
    )

    assert len(records) == 1
    assert records[0].provider == "openai"
    assert records[0].model == "openai:gpt-test"
    assert records[0].input_tokens == 50
    assert records[0].output_tokens == 13
    assert records[0].total_tokens == 63
    assert len(records[0].usage_metadata["calls"]) == 2


async def test_runtime_events_are_serialized_with_independent_sessions(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async def fake_invoker(**kwargs):
        sink = kwargs["event_sink"]
        await asyncio.gather(
            sink(
                RuntimeEvent(
                    "tool.started",
                    "tool",
                    content={"title": "并行任务一"},
                    metadata={"call_id": "tool-1", "tool_name": "create_task_item"},
                )
            ),
            sink(
                RuntimeEvent(
                    "tool.started",
                    "tool",
                    content={"title": "并行任务二"},
                    metadata={"call_id": "tool-2", "tool_name": "create_task_item"},
                )
            ),
        )
        return {"messages": [AIMessage(content="完成")]}

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
    )
    request = CommandRequest(message="创建两个任务")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)

    from dayboard.app.runs import AgentRunService

    events = await AgentRunService(db_session).list_events(tenant_context, run_id)
    starts = [event for event in events if event.event_type == "tool_call_started"]
    assert [event.seq for event in starts] == sorted(event.seq for event in starts)
    assert {event.event_metadata["call_id"] for event in starts} == {"tool-1", "tool-2"}


async def test_model_lifecycle_is_audited_without_user_stream_publication(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    class RecordingBridge:
        def __init__(self) -> None:
            self.events: list[str] = []

        async def publish(self, run_id, event, data, namespace=()):
            del run_id, data, namespace
            self.events.append(event)

    async def fake_invoker(**kwargs):
        sink = kwargs["event_sink"]
        await sink(
            RuntimeEvent(
                "model.completed",
                "model",
                metadata={
                    "call_id": "model-1",
                    "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
                },
            )
        )
        await sink(
            RuntimeEvent(
                "tool.started",
                "tool",
                content={"title": "会议"},
                metadata={"call_id": "tool-1", "tool_name": "create_task_item"},
            )
        )
        return {"messages": [AIMessage(content="完成")]}

    bridge = RecordingBridge()
    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
        stream_bridge=bridge,
    )
    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)

    from dayboard.app.runs import AgentRunService

    events = await AgentRunService(db_session).list_events(tenant_context, run_id)
    assert "agent_model_completed" in {event.event_type for event in events}
    assert "tool_call_started" in {event.event_type for event in events}
    assert "agent_model_completed" not in bridge.events
    assert "tool_call_started" in bridge.events


async def test_command_service_does_not_invent_missing_provider_usage(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async def fake_invoker(**kwargs):
        del kwargs
        return {"messages": [AIMessage(content="完成")]}

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
    )

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, request, run_id)

    assert await ProviderUsageRepository(db_session).list_for_run(tenant_context, run_id) == []


@pytest.mark.parametrize("error", [RuntimeError("provider failed"), asyncio.CancelledError()])
async def test_command_service_settles_usage_when_invocation_does_not_return(
    db_session: AsyncSession,
    tenant_context: TenantContext,
    error: BaseException,
) -> None:
    async def fake_invoker(**kwargs):
        await kwargs["event_sink"](
            RuntimeEvent(
                "model.completed",
                "model",
                metadata={
                    "call_id": "charged-call",
                    "usage": {"input_tokens": 11, "output_tokens": 4, "total_tokens": 15},
                },
            )
        )
        raise error

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
    )
    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)

    with pytest.raises(type(error)):
        await service.execute_command_run(tenant_context, request, run_id)

    records = await ProviderUsageRepository(db_session).list_for_run(tenant_context, run_id)
    assert len(records) == 1
    assert records[0].total_tokens == 15


async def test_provider_usage_settlement_is_idempotent(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    repository = ProviderUsageRepository(db_session)
    run_id = await CommandService(
        db_session,
        settings=Settings(DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://"),
    ).create_command_run(tenant_context, CommandRequest(message="安排会议"))
    values = {
        "run_id": run_id,
        "provider": "openai",
        "model": "openai:gpt-test",
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
        "usage_metadata": {"calls": [{"call_id": "call-1"}]},
    }

    first = await repository.settle(tenant_context, **values)
    repeated = await repository.settle(
        tenant_context, **{**values, "total_tokens": 13}
    )
    await db_session.commit()

    records = await repository.list_for_run(tenant_context, run_id)
    assert len(records) == 1
    assert first.created is True
    assert repeated.created is False
    assert records[0].total_tokens == 12


async def test_provider_usage_is_owner_scoped_within_a_tenant(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    repository = ProviderUsageRepository(db_session)
    run_id = uuid4()
    await repository.create(
        tenant_context,
        run_id=run_id,
        provider="openai",
        model="openai:gpt-test",
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
    )
    await db_session.commit()
    other_context = TenantContext(
        tenant_id=tenant_context.tenant_id,
        user_id=uuid4(),
        timezone=tenant_context.timezone,
        locale=tenant_context.locale,
    )

    assert await repository.list_for_run(other_context, run_id) == []
