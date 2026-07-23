from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.reminders import ReminderService
from dayboard.app.scheduling import SchedulingService
from agent_platform.identity import TenantContext
from dayboard.domain.calendar import CalendarEntryCreate, CalendarTimingKind, Reminder
from dayboard.domain.reminders import ReminderDeliveryStatus, ReminderSourceStatus
from dayboard.domain.tasks import TaskItemCreate, TaskItemUpdate, TaskStatus
from dayboard.db.models import ReminderDeliveryRow


def test_reminder_accepts_zero_and_normalizes_short_fixed_duration() -> None:
    assert Reminder(offset="PT15M").as_timedelta() == timedelta(minutes=15)
    assert Reminder(offset="0m").offset == "PT0M"
    assert Reminder(offset="PT0M").as_timedelta() == timedelta(0)
    assert Reminder(offset="1h").offset == "PT1H"
    with pytest.raises(ValidationError):
        Reminder(offset="P1M")


async def test_calendar_reminder_reschedule_replaces_pending_delivery(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = SchedulingService(db_session)
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

    before = await ReminderService(db_session).list_for_user(tenant_context)
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

    after = await ReminderService(db_session).list_for_user(tenant_context)
    assert [delivery.status for delivery in after].count(ReminderDeliveryStatus.cancelled) == 1
    pending = [delivery for delivery in after if delivery.status == ReminderDeliveryStatus.pending]
    assert len(pending) == 1
    assert pending[0].scheduled_for == moved_start - timedelta(minutes=30)


async def test_task_completion_cancels_pending_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = SchedulingService(db_session)
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
    deliveries = await ReminderService(db_session).list_for_user(tenant_context)
    assert [delivery.status for delivery in deliveries] == [ReminderDeliveryStatus.cancelled]


async def test_due_in_app_reminder_is_delivered_once_and_tenant_scoped(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = SchedulingService(db_session)
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

    reminders = ReminderService(db_session)
    first = await reminders.deliver_due_in_app()
    second = await reminders.deliver_due_in_app()
    assert len(first) == 1
    assert second == []

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
    await SchedulingService(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="产品会",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="0m"),
        ),
    )

    deliveries = await ReminderService(db_session).list_for_user(tenant_context)
    assert len(deliveries) == 1
    assert deliveries[0].scheduled_for == start
    assert deliveries[0].status == ReminderDeliveryStatus.pending


async def test_past_calendar_entry_does_not_enqueue_a_late_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await SchedulingService(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="已经结束的日程",
            start_time=datetime.now(UTC) - timedelta(hours=1),
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT0M"),
        ),
    )

    assert await ReminderService(db_session).list_for_user(tenant_context) == []


async def test_future_calendar_entry_with_missed_offset_reminds_immediately(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    start = datetime.now(UTC) + timedelta(minutes=5)
    await SchedulingService(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="即将开始的日程",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )

    delivered = await ReminderService(db_session).deliver_due_in_app()
    assert len(delivered) == 1


async def test_worker_recovery_expires_reminder_after_calendar_start(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = SchedulingService(db_session)
    entry = await scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="恢复时已经结束",
            start_time=datetime.now(UTC) + timedelta(hours=1),
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT2H"),
        ),
    )
    row = await scheduling.calendar_entries.get(tenant_context, entry.id)
    assert row is not None
    row.start_time = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    assert await ReminderService(db_session).deliver_due_in_app() == []
    deliveries = await ReminderService(db_session).list_for_user(tenant_context)
    assert [delivery.status for delivery in deliveries] == [ReminderDeliveryStatus.cancelled]


async def test_reminder_inbox_uses_current_source_time_and_hides_pending_queue(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = SchedulingService(db_session)
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
    await ReminderService(db_session).deliver_due_in_app()

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

    queue = await ReminderService(db_session).list_for_user(tenant_context)
    inbox = await ReminderService(db_session).list_inbox(tenant_context)
    assert {item.status for item in queue} == {
        ReminderDeliveryStatus.delivered,
        ReminderDeliveryStatus.pending,
    }
    assert len(inbox) == 1
    assert inbox[0].status == ReminderDeliveryStatus.delivered
    assert inbox[0].source_status == ReminderSourceStatus.scheduled
    assert inbox[0].source_occurs_at == moved_start


async def test_reminder_inbox_marks_deleted_source_unavailable(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scheduling = SchedulingService(db_session)
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
    await ReminderService(db_session).deliver_due_in_app()
    row = await scheduling.calendar_entries.get(tenant_context, entry.id)
    assert row is not None
    row.deleted_at = datetime.now(UTC)
    await db_session.commit()

    inbox = await ReminderService(db_session).list_inbox(tenant_context)
    assert len(inbox) == 1
    assert inbox[0].source_status == ReminderSourceStatus.deleted


async def test_reminder_inbox_api_marks_read_retries_failure_and_isolates_tenant(
    api_app,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    start = datetime.now(UTC) + timedelta(minutes=1)
    await SchedulingService(db_session).create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="提醒中心验收",
            start_time=start,
            timezone="Asia/Shanghai",
            reminder=Reminder(offset="PT10M"),
        ),
    )
    await ReminderService(db_session).deliver_due_in_app()

    foreign = ReminderDeliveryRow(
        tenant_id=uuid4(),
        owner_user_id=uuid4(),
        source_type="calendar_entry",
        source_id=uuid4(),
        channel="in_app",
        scheduled_for=datetime.now(UTC),
        status=ReminderDeliveryStatus.delivered.value,
        payload={"title": "其他租户"},
    )
    db_session.add(foreign)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        listed = await client.get("/api/reminders")
        assert listed.status_code == 200
        assert [item["payload"]["title"] for item in listed.json()] == ["提醒中心验收"]
        reminder_id = listed.json()[0]["id"]
        assert listed.json()[0]["read_at"] is None
        assert listed.json()[0]["source_status"] == "scheduled"
        assert datetime.fromisoformat(listed.json()[0]["source_occurs_at"]) == start

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
