from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.composition.platform import build_platform_services, build_run_service
from dayboard.app.clarifications import ClarificationService
from dayboard.app.run_recovery import recover_stale_queued_runs, recover_stale_running_runs
from agent_platform.core import ActiveThreadRunError, EventExtensionEnvelope, UserContext
from dayboard.db.run_repositories import AgentRunEventRepository
from dayboard.db.models import AgentRunRow, IdempotencyKeyRow
from dayboard.db.session import SessionLocal
from dayboard.db.run_repositories import PostgresIdempotencyStore
from agent_platform.core import AgentRunStatus
from dayboard.domain.interactions import ClarificationPayload


async def _create_run(
    session: AsyncSession,
    context: UserContext,
    service,
    message: str,
):
    thread = await build_platform_services(session).conversations.create_thread(context)
    return await service.create_run(
        context,
        thread_id=thread.id,
        first_human_message=message,
    )


async def test_agent_run_service_records_lifecycle_events(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)

    run = await _create_run(db_session, user_context, service, "安排明天的事情")
    await service.mark_running(user_context, run)
    await service.mark_needs_clarification(user_context, run, question="需要几点？")
    await db_session.commit()
    refreshed = await service.get_run(user_context, run.id)

    events = await AgentRunEventRepository(db_session).list_for_run(user_context, run.id)

    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.needs_clarification
    assert [event.seq for event in events] == [1, 2, 3]
    assert [event.event_type for event in events] == [
        "run.created",
        "run.started",
        "run.needs_clarification",
    ]
    assert events[-1].content == "需要几点？"


async def test_run_event_extension_round_trips(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "安排会议")
    aware_time = datetime.now(UTC)
    await service.append_progress(
        user_context,
        run.thread_id,
        run.id,
        event_type="time_resolved",
        content="时间已识别",
        extension=EventExtensionEnvelope(
            kind="dayboard.time-resolution",
            schema_version=1,
            payload={"start_time": aware_time.isoformat()},
        ),
    )
    await db_session.commit()

    events = await service.list_events(user_context, run.id)

    assert events[-1].extension is not None
    assert events[-1].extension.kind == "dayboard.time-resolution"
    assert events[-1].extension.schema_version == 1
    assert events[-1].extension.payload == {"start_time": aware_time.isoformat()}


async def test_concurrent_run_events_receive_unique_ordered_sequences(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "并发事件")
    await db_session.commit()

    async def append_progress(content: str) -> None:
        async with SessionLocal() as event_session:
            event_service = build_run_service(event_session)
            await event_service.append_progress(
                user_context,
                run.thread_id,
                run.id,
                event_type="parallel_progress",
                content=content,
            )
            await event_session.commit()

    await asyncio.gather(append_progress("first"), append_progress("second"))

    events = await service.list_events(user_context, run.id)
    assert [event.seq for event in events] == [1, 2, 3]
    assert {event.content for event in events[1:]} == {"first", "second"}


async def test_stale_running_runs_are_recovered_to_failed(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "安排会议")
    await service.mark_running(user_context, run)
    stale_at = datetime.now(UTC) - timedelta(minutes=20)
    await db_session.execute(
        update(AgentRunRow).where(AgentRunRow.id == run.id).values(updated_at=stale_at)
    )
    await db_session.commit()

    recovered = await recover_stale_running_runs(
        service,
        updated_before=datetime.now(UTC) - timedelta(minutes=10),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    await db_session.commit()
    refreshed = await service.get_run(user_context, run.id)
    events = await service.list_events(user_context, run.id)

    assert recovered == [run.id]
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.failed
    assert events[-1].event_type == "run.failed"
    assert events[-1].extension is not None
    assert events[-1].extension.kind == "agent-platform.failure"
    assert events[-1].extension.payload["error_type"] == "StaleRunRecovered"


async def test_stale_queued_runs_are_recovered_without_touching_recent_runs(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    stale = await _create_run(db_session, user_context, service, "旧请求")
    recent = await _create_run(db_session, user_context, service, "新请求")
    stale_at = datetime.now(UTC) - timedelta(minutes=40)
    await db_session.execute(
        update(AgentRunRow).where(AgentRunRow.id == stale.id).values(created_at=stale_at)
    )
    await db_session.commit()

    recovered = await recover_stale_queued_runs(
        service,
        created_before=datetime.now(UTC) - timedelta(minutes=30),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    await db_session.commit()
    refreshed_stale = await service.get_run(user_context, stale.id)
    refreshed_recent = await service.get_run(user_context, recent.id)
    events = await service.list_events(user_context, stale.id)

    assert recovered == [stale.id]
    assert refreshed_stale is not None
    assert refreshed_stale.status == AgentRunStatus.failed
    assert refreshed_stale.last_ai_message == "排队超时，请重试"
    assert refreshed_recent is not None
    assert refreshed_recent.status == AgentRunStatus.queued
    assert events[-1].event_type == "run.failed"
    assert events[-1].extension is not None
    assert events[-1].extension.kind == "agent-platform.failure"
    assert events[-1].extension.payload["error_type"] == "QueueWaitTimeout"


async def test_queued_timeout_cannot_fail_a_run_that_has_started(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "正在启动")
    await service.mark_running(user_context, run)

    transitioned = await service.mark_failed(
        user_context,
        run,
        error_type="QueueWaitTimeout",
        error_message="排队超时，请重试",
        from_statuses={AgentRunStatus.queued},
    )
    await db_session.commit()
    events = await service.list_events(user_context, run.id)
    refreshed = await service.get_run(user_context, run.id)

    assert not transitioned
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.running
    assert [event.event_type for event in events] == ["run.created", "run.started"]


async def test_run_reads_refresh_status_changed_by_another_session(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "安排会议")
    await service.mark_running(user_context, run)
    await db_session.commit()

    async with SessionLocal() as cancelling_session:
        cancelling = build_run_service(cancelling_session)
        other_run = await cancelling.get_run(user_context, run.id)
        assert other_run is not None
        await cancelling.mark_cancelled(user_context, other_run)
        await cancelling_session.commit()

    refreshed = await service.get_run(user_context, run.id)

    assert refreshed is not None
    assert refreshed.status == "cancelled"


async def test_cancelled_run_cannot_be_completed_by_worker_with_stale_state(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "安排会议")
    await service.mark_running(user_context, run)
    await db_session.commit()

    async with SessionLocal() as worker_session, SessionLocal() as cancelling_session:
        worker = build_run_service(worker_session)
        cancelling = build_run_service(cancelling_session)
        worker_run = await worker.get_run(user_context, run.id)
        cancelling_run = await cancelling.get_run(user_context, run.id)
        assert worker_run is not None
        assert cancelling_run is not None

        assert await cancelling.mark_cancelled(user_context, cancelling_run)
        await cancelling_session.commit()
        assert not await worker.mark_completed(
            user_context,
            worker_run,
            result_message="不应覆盖取消状态",
        )
        await worker_session.commit()

    refreshed = await service.get_run(user_context, run.id)
    events = await service.list_events(user_context, run.id)
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.cancelled.value
    assert [event.event_type for event in events] == [
        "run.created",
        "run.started",
        "run.cancelled",
    ]


async def test_completed_run_cannot_be_cancelled_by_request_with_stale_state(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "安排会议")
    await service.mark_running(user_context, run)
    await db_session.commit()

    async with SessionLocal() as worker_session, SessionLocal() as cancelling_session:
        worker = build_run_service(worker_session)
        cancelling = build_run_service(cancelling_session)
        worker_run = await worker.get_run(user_context, run.id)
        cancelling_run = await cancelling.get_run(user_context, run.id)
        assert worker_run is not None
        assert cancelling_run is not None

        assert await worker.mark_completed(
            user_context,
            worker_run,
            result_message="已完成",
        )
        await worker_session.commit()
        assert not await cancelling.mark_cancelled(user_context, cancelling_run)
        await cancelling_session.commit()

    refreshed = await service.get_run(user_context, run.id)
    events = await service.list_events(user_context, run.id)
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.completed.value
    assert refreshed.last_ai_message == "已完成"
    assert [event.event_type for event in events] == [
        "run.created",
        "run.started",
        "run.completed",
    ]


async def test_expired_idempotency_keys_are_deleted(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    repository = PostgresIdempotencyStore(db_session)
    old = await repository.claim(
        user_context,
        key="old-key",
        request_hash="a" * 64,
        run_id=uuid4(),
    )
    await repository.claim(
        user_context,
        key="new-key",
        request_hash="b" * 64,
        run_id=uuid4(),
    )
    cutoff = datetime.now(UTC) - timedelta(days=7)
    await db_session.execute(
        update(IdempotencyKeyRow)
        .where(IdempotencyKeyRow.id == old.record.id)
        .values(created_at=cutoff - timedelta(seconds=1))
    )
    await db_session.commit()

    deleted = await repository.delete_created_before(cutoff)
    await db_session.commit()
    remaining = await db_session.scalars(
        select(IdempotencyKeyRow.key).order_by(IdempotencyKeyRow.key)
    )

    assert deleted == 1
    assert list(remaining) == ["new-key"]


async def test_failed_command_submission_rolls_back_its_idempotency_claim(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    platform = build_platform_services(db_session)
    thread = await platform.conversations.create_thread(user_context, title="同一会话")
    source = await platform.runs.create_run(
        user_context,
        first_human_message="需要选择",
        thread_id=thread.id,
    )
    assert await platform.runs.mark_running(user_context, source)
    assert await platform.runs.mark_needs_clarification(
        user_context,
        source,
        question="选择哪一个？",
    )
    pending = await ClarificationService(platform.conversations).set_pending(
        user_context,
        thread_id=thread.id,
        run_id=source.id,
        question="选择哪一个？",
        payload=ClarificationPayload(response_kind="free_text"),
    )
    active = await platform.runs.create_run(
        user_context,
        first_human_message="正在执行",
        thread_id=thread.id,
    )
    await platform.unit_of_work.commit()

    with pytest.raises(ActiveThreadRunError):
        await platform.submissions.submit(
            user_context,
            input_message="第二条命令",
            thread_id=thread.id,
            idempotency_key="retry-after-active-run",
            request_identity="same-request",
            consume_interaction_version=pending.version,
        )

    persisted_key = await db_session.scalar(
        select(IdempotencyKeyRow.id).where(
            IdempotencyKeyRow.user_id == user_context.user_id,
            IdempotencyKeyRow.key == "retry-after-active-run",
        )
    )
    assert persisted_key is None
    persisted_state = await platform.conversations.get_state(user_context, thread.id)
    assert persisted_state is not None
    assert persisted_state.interaction == pending.interaction
    assert persisted_state.version == pending.version

    assert await platform.runs.mark_cancelled(user_context, active)
    await platform.unit_of_work.commit()
    retried = await platform.submissions.submit(
        user_context,
        input_message="第二条命令",
        thread_id=thread.id,
        idempotency_key="retry-after-active-run",
        request_identity="same-request",
        consume_interaction_version=pending.version,
    )
    assert retried.created
    consumed_state = await platform.conversations.get_state(user_context, thread.id)
    assert consumed_state is not None
    assert consumed_state.interaction is None
    assert consumed_state.version == pending.version + 1


async def test_run_lookup_is_owner_scoped_within_a_user(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_run_service(db_session)
    run = await _create_run(db_session, user_context, service, "安排会议")
    other_context = UserContext(
        user_id=uuid4(),
        timezone=user_context.timezone,
        locale=user_context.locale,
    )

    assert await service.get_run(other_context, run.id) is None
