from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.runs import AgentRunService
from agent_platform.identity import TenantContext
from dayboard.db.run_repositories import AgentRunEventRepository
from dayboard.db.models import AgentRunRow, IdempotencyKeyRow
from dayboard.db.session import SessionLocal
from dayboard.db.run_repositories import IdempotencyKeyRepository
from agent_platform.runs import AgentRunStatus


async def test_agent_run_service_records_lifecycle_events(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)

    run = await service.create_run(tenant_context, input_message="安排明天的事情")
    await service.mark_running(tenant_context, run)
    await service.mark_needs_clarification(tenant_context, run, question="需要几点？")
    await db_session.commit()
    await db_session.refresh(run)

    events = await AgentRunEventRepository(db_session).list_for_run(tenant_context, run.id)

    assert run.status == AgentRunStatus.needs_clarification.value
    assert [event.seq for event in events] == [1, 2, 3]
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "clarification_requested",
    ]
    assert events[-1].content == "需要几点？"


async def test_run_event_metadata_serializes_datetime(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    aware_time = datetime.now(UTC)
    await service.append_progress(
        tenant_context,
        run.id,
        event_type="time_resolved",
        content="时间已识别",
        event_metadata={"start_time": aware_time},
    )
    await db_session.commit()

    events = await service.list_events(tenant_context, run.id)

    assert events[-1].event_metadata == {"start_time": aware_time.isoformat()}


async def test_stale_running_runs_are_recovered_to_failed(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    await service.mark_running(tenant_context, run)
    stale_at = datetime.now(UTC) - timedelta(minutes=20)
    await db_session.execute(
        update(AgentRunRow).where(AgentRunRow.id == run.id).values(updated_at=stale_at)
    )
    await db_session.commit()

    recovered = await service.recover_stale_running(
        updated_before=datetime.now(UTC) - timedelta(minutes=10),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    await db_session.commit()
    await db_session.refresh(run)
    events = await service.list_events(tenant_context, run.id)

    assert recovered == [run.id]
    assert run.status == "failed"
    assert events[-1].event_type == "run_failed"
    assert events[-1].event_metadata["error_type"] == "StaleRunRecovered"


async def test_stale_queued_runs_are_recovered_without_touching_recent_runs(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    stale = await service.create_run(tenant_context, input_message="旧请求")
    recent = await service.create_run(tenant_context, input_message="新请求")
    stale_at = datetime.now(UTC) - timedelta(minutes=40)
    await db_session.execute(
        update(AgentRunRow).where(AgentRunRow.id == stale.id).values(created_at=stale_at)
    )
    await db_session.commit()

    recovered = await service.recover_stale_queued(
        created_before=datetime.now(UTC) - timedelta(minutes=30),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    await db_session.commit()
    await db_session.refresh(stale)
    await db_session.refresh(recent)
    events = await service.list_events(tenant_context, stale.id)

    assert recovered == [stale.id]
    assert stale.status == AgentRunStatus.failed.value
    assert stale.result_message == "排队超时，请重试"
    assert recent.status == AgentRunStatus.queued.value
    assert events[-1].event_type == "run_failed"
    assert events[-1].event_metadata["error_type"] == "QueueWaitTimeout"


async def test_queued_timeout_cannot_fail_a_run_that_has_started(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="正在启动")
    await service.mark_running(tenant_context, run)

    transitioned = await service.mark_failed(
        tenant_context,
        run,
        error_type="QueueWaitTimeout",
        error_message="排队超时，请重试",
        from_statuses={AgentRunStatus.queued},
    )
    await db_session.commit()
    events = await service.list_events(tenant_context, run.id)

    assert not transitioned
    assert run.status == AgentRunStatus.running.value
    assert [event.event_type for event in events] == ["run_created", "run_started"]


async def test_run_reads_refresh_status_changed_by_another_session(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    await service.mark_running(tenant_context, run)
    await db_session.commit()

    async with SessionLocal() as cancelling_session:
        cancelling = AgentRunService(cancelling_session)
        other_run = await cancelling.get_run_row(tenant_context, run.id)
        assert other_run is not None
        await cancelling.mark_cancelled(tenant_context, other_run)
        await cancelling_session.commit()

    refreshed = await service.get_run_row(tenant_context, run.id)

    assert refreshed is not None
    assert refreshed.status == "cancelled"


async def test_cancelled_run_cannot_be_completed_by_worker_with_stale_state(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    await service.mark_running(tenant_context, run)
    await db_session.commit()

    async with SessionLocal() as worker_session, SessionLocal() as cancelling_session:
        worker = AgentRunService(worker_session)
        cancelling = AgentRunService(cancelling_session)
        worker_run = await worker.get_run_row(tenant_context, run.id)
        cancelling_run = await cancelling.get_run_row(tenant_context, run.id)
        assert worker_run is not None
        assert cancelling_run is not None

        assert await cancelling.mark_cancelled(tenant_context, cancelling_run)
        await cancelling_session.commit()
        assert not await worker.mark_completed(
            tenant_context,
            worker_run,
            result_message="不应覆盖取消状态",
        )
        await worker_session.commit()

    refreshed = await service.get_run_row(tenant_context, run.id)
    events = await service.list_events(tenant_context, run.id)
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.cancelled.value
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "run_cancelled",
    ]


async def test_completed_run_cannot_be_cancelled_by_request_with_stale_state(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    await service.mark_running(tenant_context, run)
    await db_session.commit()

    async with SessionLocal() as worker_session, SessionLocal() as cancelling_session:
        worker = AgentRunService(worker_session)
        cancelling = AgentRunService(cancelling_session)
        worker_run = await worker.get_run_row(tenant_context, run.id)
        cancelling_run = await cancelling.get_run_row(tenant_context, run.id)
        assert worker_run is not None
        assert cancelling_run is not None

        assert await worker.mark_completed(
            tenant_context,
            worker_run,
            result_message="已完成",
        )
        await worker_session.commit()
        assert not await cancelling.mark_cancelled(tenant_context, cancelling_run)
        await cancelling_session.commit()

    refreshed = await service.get_run_row(tenant_context, run.id)
    events = await service.list_events(tenant_context, run.id)
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.completed.value
    assert refreshed.result_message == "已完成"
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "run_completed",
    ]


async def test_expired_idempotency_keys_are_deleted(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    repository = IdempotencyKeyRepository(db_session)
    old, _ = await repository.claim(
        tenant_context,
        key="old-key",
        request_hash="a" * 64,
        run_id=uuid4(),
    )
    await repository.claim(
        tenant_context,
        key="new-key",
        request_hash="b" * 64,
        run_id=uuid4(),
    )
    cutoff = datetime.now(UTC) - timedelta(days=7)
    await db_session.execute(
        update(IdempotencyKeyRow)
        .where(IdempotencyKeyRow.id == old.id)
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


async def test_run_lookup_is_owner_scoped_within_a_tenant(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    other_context = TenantContext(
        tenant_id=tenant_context.tenant_id,
        user_id=uuid4(),
        timezone=tenant_context.timezone,
        locale=tenant_context.locale,
    )

    assert await service.get_run(other_context, run.id) is None
