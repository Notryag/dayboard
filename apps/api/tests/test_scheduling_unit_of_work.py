from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
from dayboard.app.scheduling import SchedulingService
from dayboard.db.models import CalendarEntryRow
from dayboard.db.scheduling_uow import SqlAlchemySchedulingUnitOfWork
from dayboard.domain.calendar import CalendarEntryCreate, Reminder


class ReminderWriteFailed(RuntimeError):
    pass


class FailingReminderScheduleStore:
    async def replace_pending(self, *args, **kwargs) -> None:
        del args, kwargs
        raise ReminderWriteFailed("reminder outbox write failed")


async def test_scheduling_service_leaves_commit_to_outer_transaction(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    unit_of_work = SqlAlchemySchedulingUnitOfWork(db_session)
    service = SchedulingService(unit_of_work)
    commit_calls = 0

    async def record_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1

    unit_of_work.commit = record_commit  # type: ignore[method-assign]
    start = datetime.now(UTC) + timedelta(days=1)

    entry = await service.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="外层事务提交",
            start_time=start,
            timezone=tenant_context.timezone,
            reminder=Reminder(offset="PT10M"),
        ),
    )

    assert entry.title == "外层事务提交"
    assert commit_calls == 0


async def test_reminder_failure_rolls_back_schedule_and_outbox_together(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    unit_of_work = SqlAlchemySchedulingUnitOfWork(db_session)
    unit_of_work.reminders = FailingReminderScheduleStore()  # type: ignore[assignment]
    service = SchedulingService(unit_of_work)

    with pytest.raises(ReminderWriteFailed):
        await service.create_calendar_entry(
            tenant_context,
            CalendarEntryCreate(
                title="原子回滚",
                start_time=datetime.now(UTC) + timedelta(days=1),
                timezone=tenant_context.timezone,
                reminder=Reminder(offset="PT10M"),
            ),
        )

    await unit_of_work.rollback()
    persisted = await db_session.scalar(
        select(CalendarEntryRow).where(CalendarEntryRow.title == "原子回滚")
    )
    assert persisted is None
