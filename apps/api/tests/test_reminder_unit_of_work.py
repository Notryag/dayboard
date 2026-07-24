from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext

from dayboard.app.reminders import ReminderService
from dayboard.app.scheduling_services import build_scheduling_services
from dayboard.composition.reminders import build_reminder_services
from dayboard.db.models import CalendarEntryRow, ReminderDeliveryRow
from dayboard.db.reminder_repositories import ReminderDeliveryRepository, ReminderSourceRepository
from dayboard.db.repositories import CalendarEntryRepository
from dayboard.db.session import SessionLocal
from dayboard.domain.calendar import (
    CalendarEntry,
    CalendarEntryCreate,
    CalendarTimingKind,
    Reminder,
)
from dayboard.domain.reminders import ReminderDeliveryStatus, ReminderSourceType


class ReminderSourceProjectionFailed(RuntimeError):
    pass


class FailingReminderSourceStore:
    async def list_for_deliveries(self, deliveries):
        del deliveries
        return []

    async def lock_for_deliveries(self, deliveries):
        del deliveries
        raise ReminderSourceProjectionFailed("reminder source projection failed")


class SignalingReminderSourceRepository(ReminderSourceRepository):
    def __init__(self, session: AsyncSession, lock_started: asyncio.Event) -> None:
        super().__init__(session)
        self.lock_started = lock_started

    async def lock_for_deliveries(self, deliveries):
        self.lock_started.set()
        return await super().lock_for_deliveries(deliveries)


async def _create_due_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> CalendarEntry:
    scheduling = build_scheduling_services(db_session)
    start = datetime.now(UTC) + timedelta(minutes=5)
    entry = await scheduling.scheduling.create_calendar_entry(
        tenant_context,
        CalendarEntryCreate(
            title="事务边界提醒",
            start_time=start,
            timezone=tenant_context.timezone,
            reminder=Reminder(offset="PT10M"),
        ),
    )
    await scheduling.unit_of_work.commit()
    return entry


async def test_reminder_service_leaves_commit_to_outer_transaction(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await _create_due_reminder(db_session, tenant_context)
    scope = build_reminder_services(db_session)
    commit_calls = 0

    async def record_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1

    scope.unit_of_work.commit = record_commit  # type: ignore[method-assign]
    result = await scope.reminders.process_due_in_app()

    assert len(result.delivered_ids) == 1
    assert commit_calls == 0
    await scope.unit_of_work.rollback()


async def test_source_lock_failure_leaves_due_delivery_pending(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await _create_due_reminder(db_session, tenant_context)
    scope = build_reminder_services(db_session)
    scope.unit_of_work.sources = FailingReminderSourceStore()  # type: ignore[assignment]
    service = ReminderService(scope.unit_of_work)

    with pytest.raises(ReminderSourceProjectionFailed):
        await service.process_due_in_app()
    await scope.unit_of_work.rollback()

    row = await db_session.scalar(select(ReminderDeliveryRow))
    assert row is not None
    assert row.status == ReminderDeliveryStatus.pending.value
    assert row.attempt_count == 0


async def test_concurrent_reschedule_finishes_before_worker_claims_old_reminder(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    entry = await _create_due_reminder(db_session, tenant_context)
    moved_start = entry.start_time + timedelta(days=1)

    async with SessionLocal() as schedule_session, SessionLocal() as worker_session:
        moved = await CalendarEntryRepository(schedule_session).reschedule(
            tenant_context,
            entry_id=entry.id,
            timing_kind=CalendarTimingKind.timed,
            scheduled_date=None,
            start_time=moved_start,
            end_time=None,
            expected_row_version=entry.row_version,
            updated_by_run_id=uuid4(),
            operation_key="concurrent-reschedule",
        )
        assert moved is not None

        lock_started = asyncio.Event()
        worker_scope = build_reminder_services(worker_session)
        worker_scope.unit_of_work.sources = SignalingReminderSourceRepository(
            worker_session,
            lock_started,
        )
        worker_service = ReminderService(worker_scope.unit_of_work)

        async def process_due():
            result = await worker_service.process_due_in_app()
            await worker_scope.unit_of_work.commit()
            return result

        worker_task = asyncio.create_task(process_due())
        await asyncio.wait_for(lock_started.wait(), timeout=1)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(worker_task), timeout=0.05)

        await ReminderDeliveryRepository(schedule_session).replace_pending(
            tenant_context,
            source_type=ReminderSourceType.calendar_entry,
            source_id=entry.id,
            scheduled_for=moved_start - timedelta(minutes=10),
            payload={
                "title": entry.title,
                "source_type": ReminderSourceType.calendar_entry.value,
                "source_id": str(entry.id),
                "occurs_at": moved_start.isoformat(),
                "timezone": entry.timezone,
            },
        )
        await schedule_session.commit()

        result = await asyncio.wait_for(worker_task, timeout=1)
        assert result.delivered_ids == []

    statuses = set(
        await db_session.scalars(
            select(ReminderDeliveryRow.status).where(
                ReminderDeliveryRow.source_id == entry.id,
            )
        )
    )
    assert statuses == {
        ReminderDeliveryStatus.cancelled.value,
        ReminderDeliveryStatus.pending.value,
    }
    persisted = await db_session.get(CalendarEntryRow, entry.id)
    assert persisted is not None
    assert persisted.start_time == moved_start
