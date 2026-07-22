from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, ReminderDeliveryRow, TaskItemRow
from dayboard.db.reminder_repositories import ReminderDeliveryRepository
from dayboard.domain.calendar import Reminder
from dayboard.domain.reminders import (
    ReminderDelivery,
    ReminderDeliveryStatus,
    ReminderSourceType,
)


def reminder_delivery_from_row(row: ReminderDeliveryRow) -> ReminderDelivery:
    return ReminderDelivery.model_validate(row, from_attributes=True)


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.deliveries = ReminderDeliveryRepository(session)

    async def sync_calendar_entry(self, context: TenantContext, row: CalendarEntryRow) -> None:
        now = datetime.now(UTC)
        active = (
            row.start_time is not None
            and row.start_time > now
            and row.completed_at is None
            and row.deleted_at is None
        )
        if not active:
            await self.deliveries.replace_pending(
                context,
                source_type=ReminderSourceType.calendar_entry,
                source_id=row.id,
                scheduled_for=None,
                payload=None,
            )
            return
        assert row.start_time is not None
        reminder = Reminder.model_validate(row.reminder) if row.reminder else None
        scheduled_for = row.start_time - reminder.as_timedelta() if reminder else None
        payload = (
            {
                "title": row.title,
                "source_type": ReminderSourceType.calendar_entry.value,
                "source_id": str(row.id),
                "occurs_at": row.start_time.isoformat(),
                "timezone": row.timezone,
            }
            if reminder
            else None
        )
        await self.deliveries.replace_pending(
            context,
            source_type=ReminderSourceType.calendar_entry,
            source_id=row.id,
            scheduled_for=scheduled_for,
            payload=payload,
        )

    async def sync_task_item(self, context: TenantContext, row: TaskItemRow) -> None:
        reminder = Reminder.model_validate(row.reminder) if row.reminder else None
        active = reminder is not None and row.due_at is not None and row.status == "open"
        scheduled_for = row.due_at - reminder.as_timedelta() if active else None
        payload = (
            {
                "title": row.title,
                "source_type": ReminderSourceType.task_item.value,
                "source_id": str(row.id),
                "occurs_at": row.due_at.isoformat(),
                "timezone": row.timezone,
            }
            if active
            else None
        )
        await self.deliveries.replace_pending(
            context,
            source_type=ReminderSourceType.task_item,
            source_id=row.id,
            scheduled_for=scheduled_for,
            payload=payload,
        )

    async def cancel_calendar_entry(self, context: TenantContext, row: CalendarEntryRow) -> None:
        await self.deliveries.cancel_active(
            context,
            source_type=ReminderSourceType.calendar_entry,
            source_id=row.id,
        )

    async def list_for_user(self, context: TenantContext) -> list[ReminderDelivery]:
        return [
            reminder_delivery_from_row(row) for row in await self.deliveries.list_for_user(context)
        ]

    async def mark_read(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> tuple[ReminderDelivery | None, bool]:
        row = await self.deliveries.get_for_user(context, delivery_id, for_update=True)
        if row is None:
            return None, False
        if row.status != ReminderDeliveryStatus.delivered.value:
            return reminder_delivery_from_row(row), False
        if row.read_at is None:
            row.read_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return reminder_delivery_from_row(row), True

    async def retry_failed(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> tuple[ReminderDelivery | None, bool]:
        row = await self.deliveries.get_for_user(context, delivery_id, for_update=True)
        if row is None:
            return None, False
        if row.status != ReminderDeliveryStatus.failed.value:
            return reminder_delivery_from_row(row), False
        row.status = ReminderDeliveryStatus.pending.value
        row.next_attempt_at = datetime.now(UTC)
        row.claimed_at = None
        row.last_error = None
        await self.session.commit()
        await self.session.refresh(row)
        return reminder_delivery_from_row(row), True

    async def deliver_due_in_app(self, *, limit: int = 100) -> list[str]:
        now = datetime.now(UTC)
        rows = await self.deliveries.claim_due(now=now, limit=limit, channel="in_app")
        calendar_ids = {
            row.source_id
            for row in rows
            if row.source_type == ReminderSourceType.calendar_entry.value
        }
        task_ids = {
            row.source_id for row in rows if row.source_type == ReminderSourceType.task_item.value
        }
        active_calendar_ids = set(
            await self.session.scalars(
                select(CalendarEntryRow.id).where(
                    CalendarEntryRow.id.in_(calendar_ids),
                    CalendarEntryRow.start_time > now,
                    CalendarEntryRow.completed_at.is_(None),
                    CalendarEntryRow.deleted_at.is_(None),
                )
            )
        ) if calendar_ids else set()
        active_task_ids = set(
            await self.session.scalars(
                select(TaskItemRow.id).where(
                    TaskItemRow.id.in_(task_ids),
                    TaskItemRow.status == "open",
                    TaskItemRow.deleted_at.is_(None),
                )
            )
        ) if task_ids else set()
        delivered_ids: list[str] = []
        for row in rows:
            source_is_active = (
                row.source_type == ReminderSourceType.calendar_entry.value
                and row.source_id in active_calendar_ids
            ) or (
                row.source_type == ReminderSourceType.task_item.value
                and row.source_id in active_task_ids
            )
            if not source_is_active:
                row.status = ReminderDeliveryStatus.cancelled.value
                row.claimed_at = None
                continue
            if await self.deliveries.mark_delivered(
                row.id,
                delivered_at=now,
                provider_message_id=f"in_app:{row.id}",
            ):
                delivered_ids.append(str(row.id))
        await self.session.commit()
        return delivered_ids
