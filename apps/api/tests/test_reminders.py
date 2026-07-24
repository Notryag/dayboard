from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.composition.reminders import build_reminder_services
from dayboard.app.reminders import (
    DeliveryDisposition,
    ReminderService,
    delivery_disposition,
)
from dayboard.app.scheduling_services import build_scheduling_service
from agent_platform.core import TenantContext
from dayboard.domain.calendar import CalendarEntryCreate, CalendarTimingKind, Reminder
from dayboard.domain.reminders import (
    CALENDAR_REMINDER_DELIVERY_GRACE,
    ReminderDelivery,
    ReminderDeliveryStatus,
    ReminderSourceSnapshot,
    ReminderSourceStatus,
    ReminderSourceType,
)
from dayboard.domain.tasks import TaskItemCreate, TaskItemUpdate, TaskStatus
from dayboard.db.models import CalendarEntryRow, ReminderDeliveryRow
from dayboard.db.reminder_repositories import ReminderDeliveryRepository, ReminderSourceRepository


def test_reminder_accepts_zero_and_normalizes_short_fixed_duration() -> None:
    assert Reminder(offset="PT15M").as_timedelta() == timedelta(minutes=15)
    assert Reminder(offset="0m").offset == "PT0M"
    assert Reminder(offset="PT0M").as_timedelta() == timedelta(0)
    assert Reminder(offset="1h").offset == "PT1H"
    with pytest.raises(ValidationError):
        Reminder(offset="P1M")


def test_delivery_disposition_distinguishes_expiry_cancellation_and_overdue_tasks() -> None:
    now = datetime.now(UTC)
    common = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "owner_user_id": uuid4(),
        "channel": "in_app",
        "scheduled_for": now - timedelta(minutes=1),
        "status": ReminderDeliveryStatus.processing,
        "attempt_count": 1,
        "next_attempt_at": None,
        "delivered_at": None,
        "read_at": None,
        "provider_message_id": None,
        "last_error": None,
        "payload": {},
        "created_at": now,
        "updated_at": now,
    }
    calendar = ReminderDelivery(
        **common,
        source_type=ReminderSourceType.calendar_entry,
        source_id=uuid4(),
    )
    calendar_source = ReminderSourceSnapshot(
        tenant_id=calendar.tenant_id,
        owner_user_id=calendar.owner_user_id,
        source_type=calendar.source_type,
        source_id=calendar.source_id,
        title="已经开始",
        status=ReminderSourceStatus.scheduled,
        occurs_at=now,
    )
    assert delivery_disposition(calendar, calendar_source, now=now) is DeliveryDisposition.deliver
    assert (
        delivery_disposition(
            calendar,
            calendar_source.model_copy(
                update={"occurs_at": now - CALENDAR_REMINDER_DELIVERY_GRACE}
            ),
            now=now,
        )
        is DeliveryDisposition.deliver
    )
    assert (
        delivery_disposition(
            calendar,
            calendar_source.model_copy(
                update={"occurs_at": now - CALENDAR_REMINDER_DELIVERY_GRACE - timedelta(seconds=1)}
            ),
            now=now,
        )
        is DeliveryDisposition.expire
    )
    assert (
        delivery_disposition(
            calendar,
            calendar_source.model_copy(update={"status": ReminderSourceStatus.completed}),
            now=now,
        )
        is DeliveryDisposition.cancel
    )

    task = ReminderDelivery(
        **common,
        source_type=ReminderSourceType.task_item,
        source_id=uuid4(),
    )
    task_source = ReminderSourceSnapshot(
        tenant_id=task.tenant_id,
        owner_user_id=task.owner_user_id,
        source_type=task.source_type,
        source_id=task.source_id,
        title="逾期待办",
        status=ReminderSourceStatus.open,
        occurs_at=now - timedelta(days=1),
    )
    assert delivery_disposition(task, task_source, now=now) is DeliveryDisposition.deliver


async def test_calendar_reminder_reschedule_replaces_pending_delivery(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(days=2)
    entry = await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="产品会议",
            start_time=start,
            end_time=start + timedelta(hours=1),
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT30M"),
        ),
    )

    before = await build_reminder_services(db_session).reminders.list_for_user(tenant_context)
    assert len(before) == 1
    assert before[0].scheduled_for == start - timedelta(minutes=30)
    assert before[0].status == ReminderDeliveryStatus.pending

    moved_start = start + timedelta(days=1)
    moved = await scheduling.reschedule_calendar_entry(
        tenant_context,
        entry_id=entry.id,
        timing_kind=CalendarTimingKind.timed,
        scheduled_date=None,
        start_time=moved_start,
        end_time=moved_start + timedelta(hours=1),
        expected_row_version=entry.row_version,
        updated_by_run_id=uuid4(),
        operation_key="move-reminder",
    )
    assert moved is not None

    after = await build_reminder_services(db_session).reminders.list_for_user(tenant_context)
    assert [delivery.status for delivery in after].count(ReminderDeliveryStatus.cancelled) == 1
    pending = [delivery for delivery in after if delivery.status == ReminderDeliveryStatus.pending]
    assert len(pending) == 1
    assert pending[0].scheduled_for == moved_start - timedelta(minutes=30)


async def test_calendar_reschedule_cancels_retryable_failed_delivery(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(days=2)
    entry = await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="改期前投递失败",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT30M"),
        ),
    )
    delivery = await db_session.scalar(select(ReminderDeliveryRow))
    assert delivery is not None
    delivery.status = ReminderDeliveryStatus.failed.value
    delivery.last_error = "temporary delivery failure"
    await db_session.commit()

    moved_start = start + timedelta(days=1)
    moved = await scheduling.reschedule_calendar_entry(
        tenant_context,
        entry_id=entry.id,
        timing_kind=CalendarTimingKind.timed,
        scheduled_date=None,
        start_time=moved_start,
        end_time=moved_start + timedelta(hours=1),
        expected_row_version=entry.row_version,
        updated_by_run_id=uuid4(),
        operation_key="replace-failed-reminder",
    )
    assert moved is not None

    deliveries = await build_reminder_services(db_session).reminders.list_for_user(tenant_context)
    assert {item.status for item in deliveries} == {
        ReminderDeliveryStatus.cancelled,
        ReminderDeliveryStatus.pending,
    }


async def test_task_completion_cancels_pending_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    task = await scheduling.create_task_item(
        tenant_context,
        TaskItemCreate(
            title="提交报告",
            due_at=datetime.now(UTC) + timedelta(days=1),
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT1H"),
        ),
    )
    assert task.reminder is not None
    assert task.reminder.anchor == "due_at"

    completed = await scheduling.update_task_item(
        tenant_context,
        task_id=task.id,
        data=TaskItemUpdate(
            status=TaskStatus.completed,
            updated_by_run_id=uuid4(),
            updated_operation_key="complete-reminder-task",
        ),
        expected_row_version=task.row_version,
    )
    assert completed is not None
    deliveries = await build_reminder_services(db_session).reminders.list_for_user(tenant_context)
    assert [delivery.status for delivery in deliveries] == [ReminderDeliveryStatus.cancelled]


async def test_due_in_app_reminder_is_delivered_once_and_tenant_scoped(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(minutes=5)
    await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="马上开始",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )

    reminders = build_reminder_services(db_session).reminders
    first = await reminders.process_due_in_app()
    second = await reminders.process_due_in_app()
    assert len(first.delivered_ids) == 1
    assert second.delivered_ids == []
    assert second.expired_ids == []
    assert second.cancelled_ids == []

    delivered = await reminders.list_for_user(tenant_context)
    assert delivered[0].status == ReminderDeliveryStatus.delivered
    assert delivered[0].attempt_count == 1
    assert delivered[0].provider_message_id == f"in_app:{delivered[0].id}"

    other_context = TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    assert await reminders.list_for_user(other_context) == []


async def test_zero_offset_reminder_is_scheduled_at_calendar_start(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    start = datetime.now(UTC) + timedelta(hours=2)
    await build_scheduling_service(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="产品会",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="0m"),
        ),
    )

    deliveries = await build_reminder_services(db_session).reminders.list_for_user(tenant_context)
    assert len(deliveries) == 1
    assert deliveries[0].scheduled_for == start
    assert deliveries[0].status == ReminderDeliveryStatus.pending


async def test_zero_offset_reminder_is_delivered_within_worker_grace(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    start = datetime.now(UTC) + timedelta(hours=1)
    await build_scheduling_service(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="按时提醒",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT0M"),
        ),
    )
    scope = build_reminder_services(db_session)
    reminders = ReminderService(
        scope.unit_of_work,
        clock=lambda: start + timedelta(seconds=15),
    )

    result = await reminders.process_due_in_app()
    assert len(result.delivered_ids) == 1
    deliveries = await reminders.list_for_user(tenant_context)
    assert deliveries[0].status is ReminderDeliveryStatus.delivered


async def test_past_calendar_entry_does_not_enqueue_a_late_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await build_scheduling_service(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="已经结束的日程",
            start_time=datetime.now(UTC) - timedelta(hours=1),
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT0M"),
        ),
    )

    assert await build_reminder_services(db_session).reminders.list_for_user(tenant_context) == []


async def test_calendar_entry_within_delivery_grace_enqueues_and_delivers_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await build_scheduling_service(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="刚刚开始",
            start_time=datetime.now(UTC) - timedelta(minutes=1),
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT0M"),
        ),
    )

    reminders = build_reminder_services(db_session).reminders
    result = await reminders.process_due_in_app()
    assert len(result.delivered_ids) == 1


async def test_future_calendar_entry_with_missed_offset_reminds_immediately(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    start = datetime.now(UTC) + timedelta(minutes=5)
    await build_scheduling_service(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="即将开始的日程",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )

    delivered = await build_reminder_services(db_session).reminders.process_due_in_app()
    assert len(delivered.delivered_ids) == 1


async def test_worker_recovery_expires_reminder_after_calendar_start(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(hours=1)
    await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="恢复时已经结束",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT2H"),
        ),
    )
    scope = build_reminder_services(db_session)
    reminders = ReminderService(
        scope.unit_of_work,
        clock=lambda: start + CALENDAR_REMINDER_DELIVERY_GRACE + timedelta(seconds=1),
    )

    result = await reminders.process_due_in_app()
    assert result.delivered_ids == []
    assert result.expired_ids != []
    deliveries = await reminders.list_for_user(tenant_context)
    assert [delivery.status for delivery in deliveries] == [ReminderDeliveryStatus.expired]


async def test_reminder_inbox_uses_current_source_time_and_hides_pending_queue(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(minutes=5)
    entry = await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="改期提醒",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )
    await build_reminder_services(db_session).reminders.process_due_in_app()

    moved_start = start + timedelta(days=1)
    moved = await scheduling.reschedule_calendar_entry(
        tenant_context,
        entry_id=entry.id,
        timing_kind=CalendarTimingKind.timed,
        scheduled_date=None,
        start_time=moved_start,
        end_time=moved_start + timedelta(hours=1),
        expected_row_version=entry.row_version,
        updated_by_run_id=uuid4(),
        operation_key="move-delivered-reminder",
    )
    assert moved is not None

    row = await db_session.get(CalendarEntryRow, entry.id)
    assert row is not None
    row.title = "改名后的提醒"
    await db_session.commit()

    reminders = build_reminder_services(db_session).reminders
    queue = await reminders.list_for_user(tenant_context)
    inbox = await reminders.list_inbox(tenant_context)
    assert {item.status for item in queue} == {
        ReminderDeliveryStatus.delivered,
        ReminderDeliveryStatus.pending,
    }
    assert len(inbox) == 1
    assert inbox[0].status == ReminderDeliveryStatus.delivered
    assert inbox[0].source_status == ReminderSourceStatus.scheduled
    assert inbox[0].source_occurs_at == moved_start
    assert inbox[0].source_title == "改名后的提醒"
    assert inbox[0].can_retry is False


async def test_reminder_inbox_marks_deleted_source_unavailable(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(minutes=5)
    entry = await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="稍后删除",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )
    await build_reminder_services(db_session).reminders.process_due_in_app()
    row = await db_session.get(CalendarEntryRow, entry.id)
    assert row is not None
    await db_session.delete(row)
    await db_session.commit()

    inbox = await build_reminder_services(db_session).reminders.list_inbox(tenant_context)
    assert len(inbox) == 1
    assert inbox[0].source_status == ReminderSourceStatus.deleted


async def test_reminder_inbox_distinguishes_cancelled_source_from_deleted_source(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = build_scheduling_service(db_session)
    start = datetime.now(UTC) + timedelta(minutes=5)
    entry = await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="主动取消",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )
    await build_reminder_services(db_session).reminders.process_due_in_app()
    cancelled = await scheduling.cancel_calendar_entry_from_ui(
        tenant_context,
        entry_id=entry.id,
        expected_row_version=entry.row_version,
    )
    assert cancelled is not None

    inbox = await build_reminder_services(db_session).reminders.list_inbox(tenant_context)
    assert len(inbox) == 1
    assert inbox[0].source_status == ReminderSourceStatus.cancelled
    assert inbox[0].source_title == "主动取消"


async def test_reminder_inbox_api_marks_read_retries_failure_and_isolates_tenant(
    api_app,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    start = datetime.now(UTC) + timedelta(minutes=1)
    entry = await build_scheduling_service(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="提醒中心验收",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )
    await build_reminder_services(db_session).reminders.process_due_in_app()

    foreign_context = TenantContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        timezone="Asia/Shanghai",
        locale="zh-CN",
    )
    foreign = ReminderDeliveryRow(
        tenant_id=foreign_context.tenant_id,
        owner_user_id=foreign_context.user_id,
        source_type="calendar_entry",
        source_id=entry.id,
        channel="in_app",
        scheduled_for=datetime.now(UTC),
        status=ReminderDeliveryStatus.delivered.value,
        payload={"title": "其他租户"},
    )
    db_session.add(foreign)
    await db_session.commit()

    foreign_delivery = (
        await ReminderDeliveryRepository(db_session).list_for_user(foreign_context)
    )[0]
    assert await ReminderSourceRepository(db_session).list_for_deliveries([foreign_delivery]) == []
    foreign_inbox = await build_reminder_services(db_session).reminders.list_inbox(foreign_context)
    assert foreign_inbox[0].source_status is ReminderSourceStatus.deleted
    assert foreign_inbox[0].source_title == "其他租户"

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        listed = await client.get("/api/reminders")
        assert listed.status_code == 200
        assert [item["payload"]["title"] for item in listed.json()] == ["提醒中心验收"]
        reminder_id = listed.json()[0]["id"]
        assert listed.json()[0]["read_at"] is None
        assert listed.json()[0]["source_status"] == "scheduled"
        assert datetime.fromisoformat(listed.json()[0]["source_occurs_at"]) == start
        assert listed.json()[0]["source_title"] == "提醒中心验收"
        assert listed.json()[0]["can_retry"] is False

        marked = await client.post(f"/api/reminders/{reminder_id}/read")
        assert marked.status_code == 200
        assert marked.json()["read_at"] is not None
        assert (await client.post(f"/api/reminders/{foreign.id}/read")).status_code == 404

        row = await db_session.get(ReminderDeliveryRow, UUID(reminder_id))
        assert row is not None
        row.status = ReminderDeliveryStatus.failed.value
        row.read_at = None
        row.last_error = "temporary delivery failure"
        await db_session.commit()

        retried = await client.post(f"/api/reminders/{reminder_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["status"] == ReminderDeliveryStatus.pending.value
        assert retried.json()["last_error"] is None
        assert (await client.get("/api/reminders")).json() == []
