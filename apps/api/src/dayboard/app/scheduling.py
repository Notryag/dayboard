from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from agent_platform.core import TenantContext

from dayboard.app.scheduling_ports import SchedulingUnitOfWork
from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, CalendarTimingKind
from dayboard.domain.reminders import CALENDAR_REMINDER_DELIVERY_GRACE, ReminderSourceType
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskItemUpdate, TaskStatus


class SchedulingService:
    def __init__(self, unit_of_work: SchedulingUnitOfWork) -> None:
        self.calendar_entries = unit_of_work.calendar_entries
        self.task_items = unit_of_work.task_items
        self.reminders = unit_of_work.reminders

    async def _sync_calendar_reminder(
        self,
        context: TenantContext,
        entry: CalendarEntry,
    ) -> None:
        active = (
            entry.start_time is not None
            and entry.start_time + CALENDAR_REMINDER_DELIVERY_GRACE >= datetime.now(UTC)
            and entry.completed_at is None
            and entry.cancelled_at is None
        )
        reminder = entry.reminder if active else None
        scheduled_for = entry.start_time - reminder.as_timedelta() if reminder else None
        payload = (
            {
                "title": entry.title,
                "source_type": ReminderSourceType.calendar_entry.value,
                "source_id": str(entry.id),
                "occurs_at": entry.start_time.isoformat(),
                "timezone": entry.timezone,
            }
            if reminder and entry.start_time is not None
            else None
        )
        await self.reminders.replace_pending(
            context,
            source_type=ReminderSourceType.calendar_entry,
            source_id=entry.id,
            scheduled_for=scheduled_for,
            payload=payload,
        )

    async def _sync_task_reminder(
        self,
        context: TenantContext,
        task: TaskItem,
    ) -> None:
        active = (
            task.reminder is not None and task.due_at is not None and task.status is TaskStatus.open
        )
        scheduled_for = (
            task.due_at - task.reminder.as_timedelta()
            if active and task.due_at is not None and task.reminder is not None
            else None
        )
        payload = (
            {
                "title": task.title,
                "source_type": ReminderSourceType.task_item.value,
                "source_id": str(task.id),
                "occurs_at": task.due_at.isoformat(),
                "timezone": task.timezone,
            }
            if active and task.due_at is not None
            else None
        )
        await self.reminders.replace_pending(
            context,
            source_type=ReminderSourceType.task_item,
            source_id=task.id,
            scheduled_for=scheduled_for,
            payload=payload,
        )

    async def create_calendar_entry(
        self,
        context: TenantContext,
        data: CalendarEntryCreate,
    ) -> CalendarEntry:
        entry = await self.calendar_entries.create(context, data)
        await self._sync_calendar_reminder(context, entry)
        return entry

    async def search_calendar_entries(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        title_query: str | None = None,
    ) -> Sequence[CalendarEntry]:
        local_zone = ZoneInfo(context.timezone)
        local_end = end_time.astimezone(local_zone)
        return await self.calendar_entries.search_active(
            context,
            start_time=start_time,
            end_time=end_time,
            start_date=start_time.astimezone(local_zone).date(),
            end_date=(
                local_end.date()
                if local_end.timetz().replace(tzinfo=None) == time.min
                else local_end.date() + timedelta(days=1)
            ),
            title_query=title_query,
        )

    async def get_calendar_entry(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        return await self.calendar_entries.get(context, entry_id)

    async def get_calendar_entry_for_update(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        return await self.calendar_entries.get_for_update(context, entry_id)

    async def get_calendar_entry_including_cancelled(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        return await self.calendar_entries.get_including_cancelled(context, entry_id)

    async def get_calendar_entry_updated_by_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        return await self.calendar_entries.get_by_updated_operation(context, run_id, operation_key)

    async def reschedule_calendar_entry(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        timing_kind: CalendarTimingKind,
        scheduled_date: date | None,
        start_time: datetime | None,
        end_time: datetime | None,
        expected_row_version: int,
        updated_by_run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        entry = await self.calendar_entries.reschedule(
            context,
            entry_id=entry_id,
            timing_kind=timing_kind,
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            expected_row_version=expected_row_version,
            updated_by_run_id=updated_by_run_id,
            operation_key=operation_key,
        )
        if entry is not None:
            await self._sync_calendar_reminder(context, entry)
        return entry

    async def get_calendar_entry_cancelled_by_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        return await self.calendar_entries.get_by_cancelled_operation(
            context,
            run_id,
            operation_key,
        )

    async def cancel_calendar_entry(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
        cancelled_by_run_id: UUID,
        operation_key: str,
        cancellation_reason: str | None,
    ) -> CalendarEntry | None:
        entry = await self.calendar_entries.cancel(
            context,
            entry_id=entry_id,
            expected_row_version=expected_row_version,
            cancelled_by_run_id=cancelled_by_run_id,
            operation_key=operation_key,
            cancellation_reason=cancellation_reason,
        )
        if entry is not None:
            await self._sync_calendar_reminder(context, entry)
        return entry

    async def get_calendar_entry_created_by_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> CalendarEntry | None:
        return await self.calendar_entries.get_by_created_run(context, run_id, operation_key)

    async def cancel_calendar_entry_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        entry = await self.calendar_entries.cancel_from_ui(
            context,
            entry_id=entry_id,
            expected_row_version=expected_row_version,
        )
        if entry is not None:
            await self._sync_calendar_reminder(context, entry)
        return entry

    async def complete_calendar_entry_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        entry = await self.calendar_entries.complete_from_ui(
            context,
            entry_id=entry_id,
            expected_row_version=expected_row_version,
        )
        if entry is not None:
            await self._sync_calendar_reminder(context, entry)
        return entry

    async def reopen_calendar_entry_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        entry = await self.calendar_entries.reopen_from_ui(
            context,
            entry_id=entry_id,
            expected_row_version=expected_row_version,
        )
        if entry is not None:
            await self._sync_calendar_reminder(context, entry)
        return entry

    async def update_calendar_entry_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        title: str,
        timing_kind: CalendarTimingKind,
        scheduled_date: date | None,
        start_time: datetime | None,
        end_time: datetime | None,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        entry = await self.calendar_entries.update_from_ui(
            context,
            entry_id=entry_id,
            title=title,
            timing_kind=timing_kind,
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            expected_row_version=expected_row_version,
        )
        if entry is not None:
            await self._sync_calendar_reminder(context, entry)
        return entry

    async def list_calendar_conflicts(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        default_duration: timedelta,
        exclude_entry_id: UUID | None = None,
    ) -> Sequence[CalendarEntry]:
        return await self.calendar_entries.list_overlapping(
            context,
            start_time=start_time,
            end_time=end_time,
            default_duration=default_duration,
            exclude_entry_id=exclude_entry_id,
        )

    async def create_task_item(
        self,
        context: TenantContext,
        data: TaskItemCreate,
    ) -> TaskItem:
        task = await self.task_items.create(context, data)
        await self._sync_task_reminder(context, task)
        return task

    async def search_task_items(
        self,
        context: TenantContext,
        *,
        title_query: str | None = None,
        status: TaskStatus | None = TaskStatus.open,
    ) -> Sequence[TaskItem]:
        return await self.task_items.search(
            context,
            title_query=title_query,
            status=status,
        )

    async def get_task_item(self, context: TenantContext, task_id: UUID) -> TaskItem | None:
        return await self.task_items.get(context, task_id)

    async def get_task_item_updated_by_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> TaskItem | None:
        return await self.task_items.get_by_updated_operation(context, run_id, operation_key)

    async def update_task_item(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        data: TaskItemUpdate,
        expected_row_version: int,
    ) -> TaskItem | None:
        task = await self.task_items.update(
            context,
            task_id=task_id,
            data=data,
            expected_row_version=expected_row_version,
        )
        if task is not None:
            await self._sync_task_reminder(context, task)
        return task

    async def get_task_item_created_by_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> TaskItem | None:
        return await self.task_items.get_by_created_run(context, run_id, operation_key)

    async def set_task_status_from_ui(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        status: TaskStatus,
        expected_row_version: int,
    ) -> TaskItem | None:
        task = await self.task_items.set_status_from_ui(
            context,
            task_id=task_id,
            status=status,
            expected_row_version=expected_row_version,
        )
        if task is not None:
            await self._sync_task_reminder(context, task)
        return task

    async def update_task_item_from_ui(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        title: str,
        due_at: datetime | None,
        expected_row_version: int,
    ) -> TaskItem | None:
        task = await self.task_items.update_from_ui(
            context,
            task_id=task_id,
            title=title,
            due_at=due_at,
            expected_row_version=expected_row_version,
        )
        if task is not None:
            await self._sync_task_reminder(context, task)
        return task
