from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.db.repositories import CalendarEntryRepository, TaskItemRepository
from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, Reminder
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskItemUpdate, TaskStatus
from dayboard.app.reminders import ReminderService


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
        created_operation_key=row.created_operation_key,
        updated_by_run_id=row.updated_by_run_id,
        updated_operation_key=row.updated_operation_key,
        cancelled_by_run_id=row.cancelled_by_run_id,
        cancelled_operation_key=row.cancelled_operation_key,
        cancellation_reason=row.cancellation_reason,
        cancelled_at=row.deleted_at,
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
        created_operation_key=row.created_operation_key,
        updated_by_run_id=row.updated_by_run_id,
        updated_operation_key=row.updated_operation_key,
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
        await ReminderService(self.session).sync_calendar_entry(context, row)
        await self.session.commit()
        await self.session.refresh(row)
        return calendar_entry_from_row(row)

    async def list_calendar_entries(self, context: TenantContext) -> Sequence[CalendarEntry]:
        rows = await self.calendar_entries.list_active(context)
        return [calendar_entry_from_row(row) for row in rows]

    async def search_calendar_entries(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        title_query: str | None = None,
    ) -> Sequence[CalendarEntry]:
        rows = await self.calendar_entries.search_active(
            context,
            start_time=start_time,
            end_time=end_time,
            title_query=title_query,
        )
        return [calendar_entry_from_row(row) for row in rows]

    async def get_calendar_entry(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.get(context, entry_id)
        return calendar_entry_from_row(row) if row else None

    async def get_calendar_entry_including_cancelled(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.get_including_cancelled(context, entry_id)
        return calendar_entry_from_row(row) if row else None

    async def get_calendar_entry_updated_by_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.get_by_updated_operation(context, run_id, operation_key)
        return calendar_entry_from_row(row) if row else None

    async def reschedule_calendar_entry(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        start_time: datetime,
        end_time: datetime,
        expected_updated_at: datetime,
        updated_by_run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.reschedule(
            context,
            entry_id=entry_id,
            start_time=start_time,
            end_time=end_time,
            expected_updated_at=expected_updated_at,
            updated_by_run_id=updated_by_run_id,
            operation_key=operation_key,
        )
        if row is None:
            return None
        await ReminderService(self.session).sync_calendar_entry(context, row)
        await self.session.commit()
        await self.session.refresh(row)
        return calendar_entry_from_row(row)

    async def get_calendar_entry_cancelled_by_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.get_by_cancelled_operation(context, run_id, operation_key)
        return calendar_entry_from_row(row) if row else None

    async def cancel_calendar_entry(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_updated_at: datetime,
        cancelled_by_run_id: UUID,
        operation_key: str,
        cancellation_reason: str | None,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.cancel(
            context,
            entry_id=entry_id,
            expected_updated_at=expected_updated_at,
            cancelled_by_run_id=cancelled_by_run_id,
            operation_key=operation_key,
            cancellation_reason=cancellation_reason,
        )
        if row is None:
            return None
        await ReminderService(self.session).cancel_calendar_entry(context, row)
        await self.session.commit()
        await self.session.refresh(row)
        return calendar_entry_from_row(row)

    async def get_calendar_entry_created_by_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> CalendarEntry | None:
        row = await self.calendar_entries.get_by_created_run(context, run_id, operation_key)
        return calendar_entry_from_row(row) if row else None

    async def list_calendar_conflicts(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        default_duration: timedelta,
        exclude_entry_id: UUID | None = None,
    ) -> Sequence[CalendarEntry]:
        rows = await self.calendar_entries.list_overlapping(
            context,
            start_time=start_time,
            end_time=end_time,
            default_duration=default_duration,
            exclude_entry_id=exclude_entry_id,
        )
        return [calendar_entry_from_row(row) for row in rows]

    async def create_task_item(
        self,
        context: TenantContext,
        data: TaskItemCreate,
    ) -> TaskItem:
        row = await self.task_items.create(context, data)
        await ReminderService(self.session).sync_task_item(context, row)
        await self.session.commit()
        await self.session.refresh(row)
        return task_item_from_row(row)

    async def list_task_items(self, context: TenantContext) -> Sequence[TaskItem]:
        rows = await self.task_items.list_active(context)
        return [task_item_from_row(row) for row in rows]

    async def search_task_items(
        self,
        context: TenantContext,
        *,
        title_query: str | None = None,
        status: TaskStatus | None = TaskStatus.open,
    ) -> Sequence[TaskItem]:
        rows = await self.task_items.search(context, title_query=title_query, status=status)
        return [task_item_from_row(row) for row in rows]

    async def get_task_item(self, context: TenantContext, task_id: UUID) -> TaskItem | None:
        row = await self.task_items.get(context, task_id)
        return task_item_from_row(row) if row else None

    async def get_task_item_updated_by_operation(
        self, context: TenantContext, run_id: UUID, operation_key: str
    ) -> TaskItem | None:
        row = await self.task_items.get_by_updated_operation(context, run_id, operation_key)
        return task_item_from_row(row) if row else None

    async def update_task_item(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        data: TaskItemUpdate,
        expected_updated_at: datetime,
    ) -> TaskItem | None:
        row = await self.task_items.update(
            context, task_id=task_id, data=data, expected_updated_at=expected_updated_at
        )
        if row is None:
            return None
        await ReminderService(self.session).sync_task_item(context, row)
        await self.session.commit()
        await self.session.refresh(row)
        return task_item_from_row(row)

    async def get_task_item_created_by_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> TaskItem | None:
        row = await self.task_items.get_by_created_run(context, run_id, operation_key)
        return task_item_from_row(row) if row else None
