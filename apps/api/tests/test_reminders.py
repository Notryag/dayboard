from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.reminders import ReminderService
from dayboard.app.scheduling import SchedulingService
from dayboard.context import TenantContext
from dayboard.domain.calendar import CalendarEntryCreate, Reminder
from dayboard.domain.reminders import ReminderDeliveryStatus
from dayboard.domain.tasks import TaskItemCreate, TaskItemUpdate, TaskStatus


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
        start_time=moved_start,
        end_time=moved_start + timedelta(hours=1),
        expected_updated_at=entry.updated_at,
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
        expected_updated_at=task.updated_at,
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
