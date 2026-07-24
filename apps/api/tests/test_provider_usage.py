from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from north import RuntimeEvent
from north.runtime import MemoryStreamBridge
import pytest
from fake_runtime import fake_executor_factory
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import AgentRunStatus, TenantContext
from dayboard.agent.budget import ProviderBudgetEstimate, ProviderBudgetGuard
from dayboard.app.command_schemas import CommandRequest
from dayboard.composition.platform import build_run_service
from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageCall,
    ProviderUsageRunNotFound,
    ProviderUsageSettlement,
)
from dayboard.agent.run_execution import DayboardRunExecutionDriver
from dayboard.composition.provider_usage import build_provider_usage_service
from dayboard.composition.commands import build_command_service
from dayboard.composition.runs import build_run_execution_scope
from dayboard.config import Settings
from dayboard.db.provider_usage_repository import ProviderUsageRepository
from dayboard.db.session import SessionLocal


def _aggregate(
    run_id,
    *,
    total_tokens: int = 12,
    call_id: str = "call-1",
) -> ProviderUsageAggregate:
    return ProviderUsageAggregate(
        run_id=run_id,
        provider="openai",
        model="openai:gpt-test",
        input_tokens=10,
        output_tokens=2,
        total_tokens=total_tokens,
        calls=(
            ProviderUsageCall(
                call_id=call_id,
                input_tokens=10,
                output_tokens=2,
                total_tokens=total_tokens,
            ),
        ),
    )


def _run_scope(
    session: AsyncSession,
    invoker,
    *,
    provider_usage=None,
    budget_guard=None,
    stream_bridge=None,
):
    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
    )
    return build_run_execution_scope(
        session,
        stream_bridge=stream_bridge or MemoryStreamBridge(),
        provider_usage=provider_usage or build_provider_usage_service(),
        budget_guard=budget_guard,
        settings=settings,
        executor_factory=fake_executor_factory(invoker),
    )


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

    scope = _run_scope(db_session, fake_invoker)
    service = build_command_service(db_session)

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await scope.execute(tenant_context, run_id)
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
    assert isinstance(records[0], ProviderUsageAggregate)
    assert [call.call_id for call in records[0].calls] == ["call-1", "call-2"]


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

    scope = _run_scope(db_session, fake_invoker)
    service = build_command_service(db_session)
    request = CommandRequest(message="创建两个任务")
    run_id = await service.create_command_run(tenant_context, request)
    await scope.execute(tenant_context, run_id)

    from dayboard.composition.platform import build_run_service

    events = await build_run_service(db_session).list_events(tenant_context, run_id)
    starts = [event for event in events if event.event_type == "tool_call_started"]
    assert [event.seq for event in starts] == sorted(event.seq for event in starts)
    assert all(event.extension is not None for event in starts)
    assert {event.extension.kind for event in starts if event.extension is not None} == {
        "north.tool-call"
    }
    assert {
        event.extension.payload["call_id"]
        for event in starts
        if event.extension is not None
    } == {"tool-1", "tool-2"}


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
    scope = _run_scope(db_session, fake_invoker, stream_bridge=bridge)
    service = build_command_service(db_session)
    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await scope.execute(tenant_context, run_id)

    from dayboard.composition.platform import build_run_service

    events = await build_run_service(db_session).list_events(tenant_context, run_id)
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

    scope = _run_scope(db_session, fake_invoker)
    service = build_command_service(db_session)

    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)
    await scope.execute(tenant_context, run_id)

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

    scope = _run_scope(db_session, fake_invoker)
    service = build_command_service(db_session)
    request = CommandRequest(message="安排会议")
    run_id = await service.create_command_run(tenant_context, request)

    with pytest.raises(type(error)):
        await scope.execute(tenant_context, run_id)

    records = await ProviderUsageRepository(db_session).list_for_run(tenant_context, run_id)
    assert len(records) == 1
    assert records[0].total_tokens == 15


async def test_provider_usage_settlement_is_idempotent(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    repository = ProviderUsageRepository(db_session)
    run_id = await build_command_service(db_session).create_command_run(
        tenant_context,
        CommandRequest(message="安排会议"),
    )
    first = await repository.settle(tenant_context, _aggregate(run_id))
    repeated = await repository.settle(
        tenant_context,
        _aggregate(run_id, total_tokens=13, call_id="retry-call"),
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
    run_id = await build_command_service(db_session).create_command_run(
        tenant_context,
        CommandRequest(message="安排会议"),
    )
    other_context = TenantContext(
        tenant_id=tenant_context.tenant_id,
        user_id=uuid4(),
        timezone=tenant_context.timezone,
        locale=tenant_context.locale,
    )
    repository = ProviderUsageRepository(db_session)

    with pytest.raises(ProviderUsageRunNotFound):
        await repository.settle(other_context, _aggregate(run_id))
    await db_session.rollback()

    assert await repository.list_for_run(tenant_context, run_id) == []
    assert await repository.list_for_run(other_context, run_id) == []

    settlement = await repository.settle(tenant_context, _aggregate(run_id))
    await db_session.commit()

    assert settlement.created is True
    assert len(await repository.list_for_run(tenant_context, run_id)) == 1


async def test_provider_usage_settlement_is_concurrent_and_immutable(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_id = await build_command_service(db_session).create_command_run(
        tenant_context,
        CommandRequest(message="安排会议"),
    )
    start = asyncio.Event()
    ready_count = 0

    async def settle(aggregate: ProviderUsageAggregate) -> ProviderUsageSettlement:
        nonlocal ready_count
        async with SessionLocal() as session:
            ready_count += 1
            if ready_count == 2:
                start.set()
            await start.wait()
            result = await ProviderUsageRepository(session).settle(tenant_context, aggregate)
            await session.commit()
            return result

    first, second = await asyncio.gather(
        settle(_aggregate(run_id, total_tokens=12, call_id="first")),
        settle(_aggregate(run_id, total_tokens=99, call_id="second")),
    )

    assert sorted([first.created, second.created]) == [False, True]
    records = await ProviderUsageRepository(db_session).list_for_run(tenant_context, run_id)
    assert len(records) == 1
    assert records[0].total_tokens in {12, 99}
    assert records[0].calls[0].call_id in {"first", "second"}


async def test_usage_failure_does_not_replace_completed_run(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    observed_statuses: list[AgentRunStatus] = []

    class FailingProviderUsage:
        async def settle(self, context, aggregate):
            async with SessionLocal() as verification_session:
                run = await build_run_service(verification_session).get_run(
                    context,
                    aggregate.run_id,
                )
                assert run is not None
                observed_statuses.append(run.status)
            raise RuntimeError("usage database unavailable")

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
        return {"messages": [AIMessage(content="完成")]}

    scope = _run_scope(
        db_session,
        fake_invoker,
        provider_usage=FailingProviderUsage(),
    )
    service = build_command_service(db_session)
    run_id = await service.create_command_run(
        tenant_context,
        CommandRequest(message="安排会议"),
    )

    await scope.execute(tenant_context, run_id)

    run = await build_run_service(db_session).get_run(tenant_context, run_id)
    assert run is not None and run.status == AgentRunStatus.completed
    assert observed_statuses == [AgentRunStatus.completed]


async def test_usage_failure_does_not_replace_provider_exception(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    class FailingProviderUsage:
        async def settle(self, context, aggregate):
            del context, aggregate
            raise RuntimeError("usage database unavailable")

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
        raise ValueError("provider failed")

    scope = _run_scope(
        db_session,
        fake_invoker,
        provider_usage=FailingProviderUsage(),
    )
    service = build_command_service(db_session)
    run_id = await service.create_command_run(
        tenant_context,
        CommandRequest(message="安排会议"),
    )

    with pytest.raises(ValueError, match="provider failed"):
        await scope.execute(tenant_context, run_id)

    run = await build_run_service(db_session).get_run(tenant_context, run_id)
    assert run is not None and run.status == AgentRunStatus.failed


async def test_budget_reconciliation_failure_does_not_replace_completed_run(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    settings = Settings(
        APP_MODEL_NAME="openai:gpt-test",
        DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
    )
    budget_guard = ProviderBudgetGuard(settings)

    def fail_reconciliation(**kwargs):
        del kwargs
        raise RuntimeError("redis unavailable")

    budget_guard.reconcile_actual = fail_reconciliation

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
        return {"messages": [AIMessage(content="完成")]}

    scope = build_run_execution_scope(
        db_session,
        stream_bridge=MemoryStreamBridge(),
        provider_usage=build_provider_usage_service(),
        settings=settings,
        budget_guard=budget_guard,
        executor_factory=fake_executor_factory(fake_invoker),
    )
    service = build_command_service(db_session)
    run_id = await service.create_command_run(
        tenant_context,
        CommandRequest(message="安排会议"),
    )

    await scope.execute(tenant_context, run_id)

    run = await build_run_service(db_session).get_run(tenant_context, run_id)
    records = await ProviderUsageRepository(db_session).list_for_run(tenant_context, run_id)
    assert run is not None and run.status == AgentRunStatus.completed
    assert len(records) == 1


async def test_duplicate_settlement_reconciles_budget_only_once(
    tenant_context: TenantContext,
) -> None:
    class IdempotentProviderUsage:
        def __init__(self) -> None:
            self.aggregates: list[ProviderUsageAggregate] = []

        async def settle(self, context, aggregate):
            del context
            self.aggregates.append(aggregate)
            return ProviderUsageSettlement(created=len(self.aggregates) == 1)

    class RecordingBudgetGuard:
        def __init__(self) -> None:
            self.actual_tokens: list[int] = []

        def reconcile_actual(self, **kwargs):
            self.actual_tokens.append(kwargs["actual_tokens"])
            return kwargs["actual_tokens"] - kwargs["estimate"].token_units

    provider_usage = IdempotentProviderUsage()
    budget_guard = RecordingBudgetGuard()
    driver = DayboardRunExecutionDriver(
        unit_of_work=SimpleNamespace(),
        conversations=SimpleNamespace(),
        runs=SimpleNamespace(),
        budget_guard=budget_guard,
        provider_usage=provider_usage,
        runtime_event_uow_factory=lambda: None,
        agent_factory=lambda context, run_id, compaction_hooks: object(),
        model_name="openai:gpt-test",
        stream_bridge=MemoryStreamBridge(),
    )
    usage_accumulator = SimpleNamespace(
        total=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
        calls=[
            {
                "call_id": "call-1",
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
            }
        ],
    )
    estimate = ProviderBudgetEstimate(token_units=5)
    run_id = uuid4()

    await driver._settle_provider_usage(
        tenant_context,
        run_id,
        usage_accumulator,
        estimate,
    )
    await driver._settle_provider_usage(
        tenant_context,
        run_id,
        usage_accumulator,
        estimate,
    )

    assert [aggregate.run_id for aggregate in provider_usage.aggregates] == [run_id, run_id]
    assert budget_guard.actual_tokens == [12]
