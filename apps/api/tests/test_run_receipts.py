from datetime import UTC, datetime, timedelta
import asyncio

import pytest
from sqlalchemy import delete, select, update

from dayboard.agent.tools import build_scheduling_tools
from dayboard.app.conversation_presentations import dayboard_presentation_parts
from dayboard.app.run_receipts import load_run_receipts, RECEIPT_EVENT
from dayboard.app.run_recovery import recover_stale_running_runs
from dayboard.composition.platform import build_platform_services
from dayboard.db.models import AgentRunEventRow, AgentRunRow, TaskItemRow
from dayboard.db.session import SessionLocal


async def running_tools(session, context):
    platform = build_platform_services(session)
    thread = await platform.conversations.create_thread(context)
    run = await platform.runs.create_run(
        context, thread_id=thread.id, first_human_message="创建任务"
    )
    await platform.runs.mark_running(context, run)
    await session.commit()
    tools = build_scheduling_tools(
        session=session,
        context=context,
        run_id=run.id,
        run_unit_of_work=platform.unit_of_work,
    )
    return platform, run, next(tool for tool in tools if tool.name == "create_task_item")


async def test_write_receipt_and_card_are_durable_before_stream_and_replay_is_once(
    db_session, user_context
):
    platform, run, tool = await running_tools(db_session, user_context)
    first = await tool.ainvoke({"title": "整理资料"})
    second = await tool.ainvoke({"title": "整理资料"})
    assert first == second
    receipts = await load_run_receipts(platform.unit_of_work, user_context, run.id)
    assert len(receipts) == 1
    assert receipts[0].part.item.value.title == "整理资料"
    async with SessionLocal() as other:
        stored = build_platform_services(other)
        receipts = await load_run_receipts(stored.unit_of_work, user_context, run.id)
        message = await stored.conversations.get_assistant_message_for_run(user_context, run.id)
        assert len(receipts) == 1
        assert (
            dayboard_presentation_parts(message.presentation)[0]["item"]["value"]["title"]
            == "整理资料"
        )
        assert len(list(await other.scalars(select(TaskItemRow)))) == 1


@pytest.mark.parametrize("failure_stage", ["receipt", "card"])
async def test_receipt_failure_rolls_back_the_business_write(
    db_session, user_context, monkeypatch, failure_stage
):
    platform, run, tool = await running_tools(db_session, user_context)

    async def fail_receipt(*args, **kwargs):
        raise RuntimeError("receipt unavailable")

    if failure_stage == "receipt":
        monkeypatch.setattr("dayboard.agent.tools.save_run_receipt", fail_receipt)
    else:
        monkeypatch.setattr(
            "dayboard.app.run_receipts.ConversationService.upsert_assistant_message", fail_receipt
        )
    with pytest.raises(RuntimeError, match="receipt unavailable"):
        await tool.ainvoke({"title": "不能留下孤立任务"})
    assert list(await db_session.scalars(select(TaskItemRow))) == []
    assert await load_run_receipts(platform.unit_of_work, user_context, run.id) == []


async def test_concurrent_retries_commit_only_one_receipt(db_session, user_context):
    platform, run, _ = await running_tools(db_session, user_context)

    async def write():
        async with SessionLocal() as session:
            other = build_platform_services(session)
            tools = build_scheduling_tools(
                session=session,
                context=user_context,
                run_id=run.id,
                run_unit_of_work=other.unit_of_work,
            )
            tool = next(tool for tool in tools if tool.name == "create_task_item")
            return await tool.ainvoke({"title": "并发重试"})

    first, second = await asyncio.gather(write(), write())
    assert first == second
    assert len(await load_run_receipts(platform.unit_of_work, user_context, run.id)) == 1
    assert len(list(await db_session.scalars(select(TaskItemRow)))) == 1


async def test_model_failure_retains_committed_card_without_a_stream_event(
    db_session, user_context
):
    from fake_runtime import fake_executor_factory
    from north.runtime import MemoryStreamBridge
    from dayboard.composition.runs import build_run_execution_scope
    from dayboard.config import Settings

    scope = None
    created = None

    async def fail_after_write(**kwargs):
        tools = build_scheduling_tools(
            session=db_session,
            context=user_context,
            run_id=created.run_id,
            run_unit_of_work=scope.platform.unit_of_work,
        )
        tool = next(tool for tool in tools if tool.name == "create_task_item")
        await tool.ainvoke({"title": "失败前已完成"})
        raise RuntimeError("model disconnected after write")

    scope = build_run_execution_scope(
        db_session,
        stream_bridge=MemoryStreamBridge(),
        settings=Settings(
            APP_MODEL_NAME="openai:test", DAYBOARD_PROVIDER_BUDGET_STORAGE_URL="memory://"
        ),
        executor_factory=fake_executor_factory(fail_after_write),
    )
    created = await scope.platform.submissions.submit(user_context, input_message="创建两个任务")
    with pytest.raises(RuntimeError, match="model disconnected"):
        await scope.execute(user_context, created.run_id)
    message = await scope.platform.conversations.get_assistant_message_for_run(
        user_context, created.run_id
    )
    assert (
        dayboard_presentation_parts(message.presentation)[0]["item"]["value"]["title"]
        == "失败前已完成"
    )


async def test_recovery_rebuilds_cards_from_receipts_without_stream_projection(
    db_session, user_context
):
    platform, run, tool = await running_tools(db_session, user_context)
    await tool.ainvoke({"title": "已完成的第一步"})
    # Remove the derived message to prove recovery uses the durable receipt.
    await db_session.execute(
        delete(AgentRunEventRow).where(
            AgentRunEventRow.run_id == run.id,
            AgentRunEventRow.event_type == "message.ai",
        )
    )
    await db_session.execute(
        update(AgentRunRow)
        .where(AgentRunRow.id == run.id)
        .values(
            updated_at=datetime.now(UTC) - timedelta(minutes=20),
        )
    )
    await db_session.commit()
    kwargs = dict(
        updated_before=datetime.now(UTC) - timedelta(minutes=10),
        timezone="Asia/Shanghai",
        locale="zh-CN",
        conversations=platform.conversations,
    )
    assert await recover_stale_running_runs(platform.runs, **kwargs) == [run.id]
    await db_session.commit()
    assert await recover_stale_running_runs(platform.runs, **kwargs) == []
    message = await platform.conversations.get_assistant_message_for_run(user_context, run.id)
    assert "部分操作已完成" in message.content
    assert "避免重复提交" in message.content
    assert (
        dayboard_presentation_parts(message.presentation)[0]["item"]["value"]["title"]
        == "已完成的第一步"
    )


async def test_cancelled_run_cannot_commit_a_late_write(db_session, user_context):
    platform, run, tool = await running_tools(db_session, user_context)
    await platform.runs.mark_cancelled(user_context, run)
    await db_session.commit()
    with pytest.raises(asyncio.CancelledError):
        await tool.ainvoke({"title": "取消后不能创建"})
    assert list(await db_session.scalars(select(TaskItemRow))) == []


async def test_cancellation_waits_for_atomic_write_and_receipt(
    db_session, user_context, monkeypatch
):
    from dayboard.app.run_receipts import save_run_receipt

    platform, run, tool = await running_tools(db_session, user_context)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def pause_receipt(*args, **kwargs):
        entered.set()
        await release.wait()
        await save_run_receipt(*args, **kwargs)

    monkeypatch.setattr("dayboard.agent.tools.save_run_receipt", pause_receipt)

    async def cancel():
        async with SessionLocal() as session:
            other = build_platform_services(session)
            latest = await other.runs.get_run_for_update(user_context, run.id)
            assert await other.runs.mark_cancelled(user_context, latest)
            await session.commit()

    writing = asyncio.create_task(tool.ainvoke({"title": "取消前已完成"}))
    cancelling = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        cancelling = asyncio.create_task(cancel())
        await asyncio.sleep(0.05)
        assert not cancelling.done()
        release.set()
        await asyncio.wait_for(writing, timeout=5)
        await asyncio.wait_for(cancelling, timeout=5)
    finally:
        release.set()
        for task in [writing, cancelling]:
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in [writing, cancelling] if task), return_exceptions=True
        )
    receipts = await load_run_receipts(platform.unit_of_work, user_context, run.id)
    assert len(receipts) == 1
    events = await platform.runs.list_events(user_context, run.id)
    assert sum(event.event_type == RECEIPT_EVENT for event in events) == 1
