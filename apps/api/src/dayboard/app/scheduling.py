from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.db.repositories import CalendarEntryRepository, TaskItemRepository
from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, Reminder
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskStatus


def calendar_entry_from_row(row: CalendarEntryRow) -> CalendarEntry:
    return CalendarEntry(
        id=row.id,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        start_time=row.start_time,
        end_time=row.end_time,
        timezone=row.timezone,
        participants=row.participants,
        reminder=Reminder.model_validate(row.reminder) if row.reminder else None,
        created_by_run_id=row.created_by_run_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def task_item_from_row(row: TaskItemRow) -> TaskItem:
    return TaskItem(
        id=row.id,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        due_at=row.due_at,
        timezone=row.timezone,
        reminder=Reminder.model_validate(row.reminder) if row.reminder else None,
        status=TaskStatus(row.status),
        created_by_run_id=row.created_by_run_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SchedulingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calendar_entries = CalendarEntryRepository(session)
        self.task_items = TaskItemRepository(session)

    async def create_calendar_entry(
        self,
        context: TenantContext,
        data: CalendarEntryCreate,
    ) -> CalendarEntry:
        row = await self.calendar_entries.create(context, data)
        await self.session.commit()
        await self.session.refresh(row)
        return calendar_entry_from_row(row)

    async def list_calendar_entries(self, context: TenantContext) -> Sequence[CalendarEntry]:
        rows = await self.calendar_entries.list_active(context)
        return [calendar_entry_from_row(row) for row in rows]

    async def get_calendar_entry_created_by_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.get_by_created_run(context, run_id)
        return calendar_entry_from_row(row) if row else None

    async def list_calendar_conflicts(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        default_duration: timedelta,
    ) -> Sequence[CalendarEntry]:
        rows = await self.calendar_entries.list_overlapping(
            context,
            start_time=start_time,
            end_time=end_time,
            default_duration=default_duration,
        )
        return [calendar_entry_from_row(row) for row in rows]

    async def create_task_item(
        self,
        context: TenantContext,
        data: TaskItemCreate,
    ) -> TaskItem:
        row = await self.task_items.create(context, data)
        await self.session.commit()
        await self.session.refresh(row)
        return task_item_from_row(row)

    async def list_task_items(self, context: TenantContext) -> Sequence[TaskItem]:
        rows = await self.task_items.list_active(context)
        return [task_item_from_row(row) for row in rows]

    async def get_task_item_created_by_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> TaskItem | None:
        row = await self.task_items.get_by_created_run(context, run_id)
        return task_item_from_row(row) if row else None
