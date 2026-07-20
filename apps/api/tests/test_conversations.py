from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import AIMessage
from north import RuntimeStreamEvent
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.app.conversations import ConversationService
from dayboard.app.runs import AgentRunService
from dayboard.config import Settings
from dayboard.context import TenantContext
from dayboard.db.session import SessionLocal
from fake_runtime import fake_executor_factory


class RecordingRunStream:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, run_id, event_type, data):
        self.events.append((run_id, event_type, data))
        return f"{len(self.events)}-0"


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
    await service.execute_command_run(tenant_context, first_request, first.run_id)
    second_request = CommandRequest(message="改到后天")
    second = await service.create_or_get_command_run(
        tenant_context,
        second_request,
        thread_id=first.thread_id,
    )
    await service.execute_command_run(tenant_context, second_request, second.run_id)

    messages = await ConversationService(db_session).list_messages(
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
                            '"id":"task-1","title":"提交周报","due_at":null,'
                            '"timezone":"Asia/Shanghai","reminder":null,"status":"open",'
                            '"created_by_run_id":"run-1",'
                            '"created_at":"2026-07-20T10:00:00Z",'
                            '"updated_at":"2026-07-20T10:00:00Z"}}'
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
    await service.execute_command_run(tenant_context, request, created.run_id)

    messages = await ConversationService(db_session).list_messages(
        tenant_context, created.thread_id
    )
    assistant = messages[-1]

    assert assistant.content == "任务已创建。"
    assert assistant.message_metadata["status"] == "completed"
    assert assistant.message_metadata["parts"][0]["tool_call_id"] == "call-1"
    assert assistant.message_metadata["parts"][0]["item"]["value"]["title"] == "提交周报"
    assert [event_type for _, event_type, _ in run_stream.events] == ["run_completed"]


async def test_cancelled_run_rejects_late_tool_message_and_failed_event(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_stream = RecordingRunStream()
    created = None

    async def fake_invoker(**kwargs):
        assert created is not None
        async with SessionLocal() as cancel_session:
            cancel_runs = AgentRunService(cancel_session)
            run = await cancel_runs.get_run_row_for_update(tenant_context, created.run_id)
            assert run is not None
            assert await cancel_runs.mark_cancelled(tenant_context, run)
            await ConversationService(cancel_session).upsert_assistant_message(
                tenant_context,
                thread_id=created.thread_id,
                run_id=created.run_id,
                content="请求已取消",
                message_metadata={"status": "cancelled", "parts": []},
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
                            '"id":"task-late","title":"不应显示","due_at":null,'
                            '"timezone":"Asia/Shanghai","reminder":null,"status":"open",'
                            '"created_by_run_id":"run-1",'
                            '"created_at":"2026-07-20T10:00:00Z",'
                            '"updated_at":"2026-07-20T10:00:00Z"}}'
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
        await service.execute_command_run(tenant_context, request, created.run_id)

    messages = await ConversationService(db_session).list_messages(
        tenant_context, created.thread_id
    )
    assistant = messages[-1]

    assert assistant.content == "请求已取消"
    assert assistant.message_metadata == {"status": "cancelled", "parts": []}
    assert run_stream.events == []


async def test_pending_clarification_state_is_versioned_and_clearable(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = ConversationService(db_session)
    thread = await service.create_thread(tenant_context)
    run_id = uuid4()

    pending = await service.set_pending_clarification(
        tenant_context,
        thread_id=thread.id,
        run_id=run_id,
        question="你指的是 8 点还是 10 点的会议？",
    )
    await db_session.commit()
    loaded = await service.get_state(tenant_context, thread.id)
    cleared = await service.clear_pending(tenant_context, thread.id)
    await db_session.commit()

    assert loaded == pending
    assert pending.pending_action == "clarification"
    assert pending.state_data == {"source_run_id": str(run_id)}
    assert pending.expires_at is not None
    assert pending.expires_at > datetime.now(UTC)
    assert cleared is not None
    assert cleared.pending_action is None
    assert cleared.pending_question is None
    assert cleared.state_data == {}
    assert cleared.version == pending.version + 1


async def test_conversation_state_is_owner_scoped(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = ConversationService(db_session)
    thread = await service.create_thread(tenant_context)
    await service.set_pending_clarification(
        tenant_context,
        thread_id=thread.id,
        run_id=uuid4(),
        question="哪一个？",
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
