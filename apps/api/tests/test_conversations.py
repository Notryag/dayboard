from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from north import RuntimeStreamEvent
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.app.clarifications import ClarificationService
from dayboard.app.conversation_presentations import (
    build_dayboard_presentation,
    dayboard_presentation_parts,
)
from dayboard.app.platform_services import build_conversation_service
from dayboard.app.platform_services import build_run_service
from dayboard.config import Settings
from agent_platform.core import AgentRunStatus, InteractionConflictError, TenantContext
from dayboard.db.session import SessionLocal
from dayboard.domain.interactions import ClarificationPayload
from fake_runtime import fake_executor_factory


class RecordingRunStream:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, run_id, event_type, data):
        self.events.append((run_id, event_type, data))
        return f"{len(self.events)}-0"


def _task_artifact(*, task_id: str, title: str) -> dict:
    return {
        "type": "schedule_item_result",
        "operation": "task_item_created",
        "item": {
            "kind": "task",
            "value": {
                "id": task_id,
                "row_version": 1,
                "title": title,
                "due_at": None,
                "timezone": "Asia/Shanghai",
                "reminder": None,
                "status": "open",
                "created_by_run_id": None,
                "created_at": "2026-07-20T10:00:00Z",
                "updated_at": "2026-07-20T10:00:00Z",
            },
        },
    }


async def test_two_runs_persist_complete_thread_history(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    invoked_threads: list[str] = []
    responses = iter(["已经安排。", "已经改好。"])

    async def fake_invoker(**kwargs):
        invoked_threads.append(kwargs["config"]["configurable"]["thread_id"])
        return {"messages": [AIMessage(content=next(responses))]}

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
    )
    first_request = CommandRequest(message="明天八点开会")
    first = await service.create_or_get_command_run(tenant_context, first_request)
    await service.execute_command_run(tenant_context, first.run_id)
    second_request = CommandRequest(message="改到后天")
    second = await service.create_or_get_command_run(
        tenant_context,
        second_request,
        thread_id=first.thread_id,
    )
    await service.execute_command_run(tenant_context, second.run_id)

    messages = await build_conversation_service(db_session).list_messages(
        tenant_context, first.thread_id
    )

    assert second.thread_id == first.thread_id
    assert invoked_threads == [str(first.thread_id), str(first.thread_id)]
    assert [(message.role.value, message.content) for message in messages] == [
        ("user", "明天八点开会"),
        ("assistant", "已经安排。"),
        ("user", "改到后天"),
        ("assistant", "已经改好。"),
    ]


async def test_tool_message_part_is_persisted_with_final_assistant_message(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_stream = RecordingRunStream()

    async def fake_invoker(**kwargs):
        await kwargs["stream_sink"](
            RuntimeStreamEvent(
                mode="messages",
                data=[
                    {
                        "type": "tool",
                        "name": "create_task_item",
                        "tool_call_id": "call-1",
                        "content": (
                            '{"type":"task_item_created","task_item":{'
                            '"id":"11111111-1111-4111-8111-111111111111",'
                            '"title":"提交周报","status":"open",'
                            '"updated_at":"2026-07-20T10:00:00Z"}}'
                        ),
                        "artifact": _task_artifact(
                            task_id="11111111-1111-4111-8111-111111111111",
                            title="提交周报",
                        ),
                    },
                    {},
                ],
            )
        )
        return {"messages": [AIMessage(content="任务已创建。")]}

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
        stream_bridge=run_stream,
    )
    request = CommandRequest(message="提醒我提交周报")
    created = await service.create_or_get_command_run(tenant_context, request)
    await service.execute_command_run(tenant_context, created.run_id)

    messages = await build_conversation_service(db_session).list_messages(
        tenant_context, created.thread_id
    )
    assistant = messages[-1]
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        history = await client.get(f"/api/threads/{created.thread_id}/messages")

    assert assistant.content == "任务已创建。"
    assert assistant.presentation is not None
    assert assistant.presentation.kind == "dayboard.schedule-results"
    assert assistant.presentation.schema_version == 1
    parts = dayboard_presentation_parts(assistant.presentation)
    assert parts[0]["tool_call_id"] == "call-1"
    assert parts[0]["item"]["value"]["title"] == "提交周报"
    assert [event_type for _, event_type, _ in run_stream.events] == ["run_completed"]
    persisted = history.json()["items"][-1]
    assert persisted["presentation"]["payload"]["parts"] == run_stream.events[0][2]["parts"]
    assert "message_metadata" not in persisted


async def test_cancelled_run_rejects_late_tool_message_and_failed_event(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_stream = RecordingRunStream()
    created = None

    async def fake_invoker(**kwargs):
        assert created is not None
        async with SessionLocal() as cancel_session:
            cancel_runs = build_run_service(cancel_session)
            run = await cancel_runs.get_run_for_update(tenant_context, created.run_id)
            assert run is not None
            assert await cancel_runs.mark_cancelled(tenant_context, run)
            await build_conversation_service(cancel_session).upsert_assistant_message(
                tenant_context,
                thread_id=created.thread_id,
                run_id=created.run_id,
                content="请求已取消",
                presentation=build_dayboard_presentation([]),
            )
            await cancel_session.commit()
        await kwargs["stream_sink"](
            RuntimeStreamEvent(
                mode="messages",
                data=[
                    {
                        "type": "tool",
                        "name": "create_task_item",
                        "tool_call_id": "late-call",
                        "content": (
                            '{"type":"task_item_created","task_item":{'
                            '"id":"22222222-2222-4222-8222-222222222222",'
                            '"title":"不应显示","status":"open",'
                            '"updated_at":"2026-07-20T10:00:00Z"}}'
                        ),
                        "artifact": _task_artifact(
                            task_id="22222222-2222-4222-8222-222222222222",
                            title="不应显示",
                        ),
                    },
                    {},
                ],
            )
        )
        raise RuntimeError("provider disconnected after cancellation")

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
        stream_bridge=run_stream,
    )
    request = CommandRequest(message="创建任务")
    created = await service.create_or_get_command_run(tenant_context, request)

    with pytest.raises(asyncio.CancelledError):
        await service.execute_command_run(tenant_context, created.run_id)

    messages = await build_conversation_service(db_session).list_messages(
        tenant_context, created.thread_id
    )
    assistant = messages[-1]

    assert assistant.content == "请求已取消"
    assert dayboard_presentation_parts(assistant.presentation) == []
    assert run_stream.events == []


async def test_clarification_outcome_is_persisted_before_terminal_stream(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_stream = RecordingRunStream()

    async def fake_invoker(**kwargs):
        del kwargs
        return {
            "thread_data": {
                "clarification": {
                    "question": "上午还是下午？",
                    "response_kind": "single_choice",
                    "options": ["上午", "下午"],
                }
            },
            "messages": [],
        }

    service = CommandService(
        db_session,
        settings=Settings(
            APP_MODEL_NAME="openai:gpt-test",
            DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://",
        ),
        executor_factory=fake_executor_factory(fake_invoker),
        stream_bridge=run_stream,
    )
    created = await service.create_or_get_command_run(
        tenant_context,
        CommandRequest(message="明天开会"),
    )

    await service.execute_command_run(tenant_context, created.run_id)

    runs = build_run_service(db_session)
    conversations = build_conversation_service(db_session)
    run = await runs.get_run(tenant_context, created.run_id)
    state = await conversations.get_state(tenant_context, created.thread_id)
    messages = await conversations.list_messages(tenant_context, created.thread_id)
    events = await runs.list_events(tenant_context, created.run_id)

    assert run is not None
    assert run.status == AgentRunStatus.needs_clarification
    assert state is not None and state.interaction is not None
    assert state.interaction.source_run_id == created.run_id
    assert messages[-1].content == "上午还是下午？"
    assert events[-1].event_type == "clarification_requested"
    assert events[-1].extension is not None
    assert events[-1].extension.kind == "agent-platform.interaction-state"
    assert events[-1].extension.payload == {"state_version": state.version}
    assert [event_type for _, event_type, _ in run_stream.events] == [
        "clarification_requested"
    ]


async def test_pending_clarification_state_is_versioned_and_clearable(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = build_conversation_service(db_session)
    thread = await service.create_thread(tenant_context)
    run_id = uuid4()

    pending = await ClarificationService(service).set_pending(
        tenant_context,
        thread_id=thread.id,
        run_id=run_id,
        question="你指的是 8 点还是 10 点的会议？",
        payload=ClarificationPayload(response_kind="free_text"),
    )
    await db_session.commit()
    loaded = await service.get_state(tenant_context, thread.id)
    cleared = await service.clear_interaction(tenant_context, thread.id)
    await db_session.commit()

    assert loaded == pending
    assert pending.interaction is not None
    assert pending.interaction.source_run_id == run_id
    assert pending.interaction.payload == {"response_kind": "free_text", "candidates": []}
    assert pending.expires_at is not None
    assert pending.expires_at > datetime.now(UTC)
    assert cleared is not None
    assert cleared.interaction is None
    assert cleared.version == pending.version + 1


async def test_conversation_state_is_owner_scoped(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = build_conversation_service(db_session)
    thread = await service.create_thread(tenant_context)
    await ClarificationService(service).set_pending(
        tenant_context,
        thread_id=thread.id,
        run_id=uuid4(),
        question="哪一个？",
        payload=ClarificationPayload(response_kind="free_text"),
    )
    await db_session.commit()
    other_context = TenantContext(
        tenant_id=tenant_context.tenant_id,
        user_id=uuid4(),
        timezone=tenant_context.timezone,
        locale=tenant_context.locale,
    )

    try:
        await service.get_state(other_context, thread.id)
    except LookupError:
        pass
    else:
        raise AssertionError("Another owner must not read conversation state")


async def test_pending_interaction_can_only_be_consumed_once_concurrently(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = build_conversation_service(db_session)
    thread = await service.create_thread(tenant_context)
    pending = await ClarificationService(service).set_pending(
        tenant_context,
        thread_id=thread.id,
        run_id=uuid4(),
        question="选择哪一个？",
        payload=ClarificationPayload(response_kind="free_text"),
    )
    await db_session.commit()

    async def consume() -> bool:
        async with SessionLocal() as session:
            contender = build_conversation_service(session)
            try:
                await contender.consume_interaction(
                    tenant_context,
                    thread_id=thread.id,
                    expected_version=pending.version,
                )
                await session.commit()
                return True
            except InteractionConflictError:
                await session.rollback()
                return False

    results = await asyncio.gather(consume(), consume())

    assert sorted(results) == [False, True]
    async with SessionLocal() as verification_session:
        consumed = await build_conversation_service(verification_session).get_state(
            tenant_context,
            thread.id,
        )
    assert consumed is not None
    assert consumed.interaction is None
    assert consumed.version == pending.version + 1
