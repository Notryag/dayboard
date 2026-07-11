from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.scheduling import SchedulingService
from dayboard.context import TenantContext
from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, Reminder
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskItemUpdate, TaskStatus


class CreateCalendarEntryInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    start_time: AwareDatetime
    end_time: AwareDatetime | None = None
    timezone: str = Field(min_length=1, max_length=64)
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = None


class CalendarEntryToolResult(BaseModel):
    type: str = "calendar_entry_created"
    calendar_entry_id: UUID
    summary: str
    calendar_entry: CalendarEntry
    conflicts: list[CalendarEntry] = Field(default_factory=list)
    requires_follow_up: bool = False


class CalendarConflictResult(BaseModel):
    type: str = "calendar_conflict"
    requested_start_time: AwareDatetime
    requested_end_time: AwareDatetime
    conflicts: list[CalendarEntry]
    summary: str
    requires_follow_up: bool = True


class SearchCalendarEntriesInput(BaseModel):
    start_time: AwareDatetime
    end_time: AwareDatetime
    title_query: str | None = Field(default=None, min_length=1, max_length=240)
    purpose: Literal["view", "reschedule", "cancel"] = "view"


class RescheduleCalendarEntryInput(BaseModel):
    calendar_entry_id: UUID
    new_date: date | None = None
    new_start_time: AwareDatetime | None = None
    expected_updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_target(self) -> RescheduleCalendarEntryInput:
        if (self.new_date is None) == (self.new_start_time is None):
            raise ValueError("provide exactly one of new_date or new_start_time")
        return self


class CalendarEntryRescheduleResult(BaseModel):
    type: str = "calendar_entry_rescheduled"
    calendar_entry_id: UUID
    previous_start_time: AwareDatetime
    previous_end_time: AwareDatetime | None
    calendar_entry: CalendarEntry
    conflicts: list[CalendarEntry] = Field(default_factory=list)
    summary: str
    requires_follow_up: bool = False


class CalendarEntryChangedError(RuntimeError):
    pass


class CancelCalendarEntryInput(BaseModel):
    calendar_entry_id: UUID
    expected_updated_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=500)


class CalendarEntryCancellationResult(BaseModel):
    type: str = "calendar_entry_cancelled"
    calendar_entry_id: UUID
    calendar_entry: CalendarEntry
    summary: str
    requires_follow_up: bool = False


class CreateTaskItemInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    due_at: AwareDatetime | None = None
    timezone: str = Field(min_length=1, max_length=64)
    reminder: Reminder | None = None
    status: TaskStatus = TaskStatus.open


class TaskItemToolResult(BaseModel):
    type: str = "task_item_created"
    task_item_id: UUID
    summary: str
    task_item: TaskItem
    requires_follow_up: bool = False


class SearchTaskItemsInput(BaseModel):
    title_query: str | None = Field(default=None, min_length=1, max_length=240)
    status: TaskStatus | None = TaskStatus.open
    purpose: Literal["view", "update", "complete", "cancel"] = "view"


class UpdateTaskItemInput(BaseModel):
    task_item_id: UUID
    expected_updated_at: AwareDatetime
    new_title: str | None = Field(default=None, min_length=1, max_length=240)
    new_due_at: AwareDatetime | None = None
    new_status: TaskStatus | None = None

    @model_validator(mode="after")
    def validate_change(self) -> UpdateTaskItemInput:
        if self.new_title is None and self.new_due_at is None and self.new_status is None:
            raise ValueError("provide at least one task change")
        return self


class TaskItemUpdateResult(BaseModel):
    type: str = "task_item_updated"
    task_item_id: UUID
    previous_task_item: TaskItem
    task_item: TaskItem
    summary: str
    requires_follow_up: bool = False


class TaskItemChangedError(RuntimeError):
    pass


async def create_calendar_entry(
    session: AsyncSession,
    context: TenantContext,
    data: CreateCalendarEntryInput,
    *,
    created_by_run_id: UUID | None = None,
    operation_key: str | None = None,
) -> CalendarEntryToolResult:
    service = SchedulingService(session)
    if created_by_run_id is not None:
        existing = await service.get_calendar_entry_created_by_run(
            context, created_by_run_id, operation_key
        )
        if existing is not None:
            return CalendarEntryToolResult(
                calendar_entry_id=existing.id,
                summary=f"{existing.title} at {existing.start_time.isoformat()}",
                calendar_entry=existing,
            )
    end_time = data.end_time or data.start_time + timedelta(hours=1)
    conflicts = await service.list_calendar_conflicts(
        context,
        start_time=data.start_time,
        end_time=end_time,
        default_duration=timedelta(hours=1),
    )
    entry = await service.create_calendar_entry(
        context,
        CalendarEntryCreate(
            **data.model_dump(exclude={"end_time"}),
            end_time=end_time,
            created_by_run_id=created_by_run_id,
            created_operation_key=operation_key,
        ),
    )
    return CalendarEntryToolResult(
        calendar_entry_id=entry.id,
        summary=(
            f"{entry.title} at {entry.start_time.isoformat()}; created with "
            f"{len(conflicts)} calendar conflict(s)."
            if conflicts
            else f"{entry.title} at {entry.start_time.isoformat()}"
        ),
        calendar_entry=entry,
        conflicts=list(conflicts),
    )


async def list_calendar_entries(
    session: AsyncSession,
    context: TenantContext,
) -> list[CalendarEntry]:
    service = SchedulingService(session)
    return list(await service.list_calendar_entries(context))


async def search_calendar_entries(
    session: AsyncSession,
    context: TenantContext,
    data: SearchCalendarEntriesInput,
) -> list[CalendarEntry]:
    return list(
        await SchedulingService(session).search_calendar_entries(
            context,
            start_time=data.start_time,
            end_time=data.end_time,
            title_query=data.title_query,
        )
    )


async def reschedule_calendar_entry(
    session: AsyncSession,
    context: TenantContext,
    data: RescheduleCalendarEntryInput,
    *,
    updated_by_run_id: UUID,
) -> CalendarEntryRescheduleResult:
    service = SchedulingService(session)
    repeated = await service.get_calendar_entry_updated_by_run(context, updated_by_run_id)
    if repeated is not None:
        return CalendarEntryRescheduleResult(
            calendar_entry_id=repeated.id,
            previous_start_time=repeated.start_time,
            previous_end_time=repeated.end_time,
            calendar_entry=repeated,
            summary=f"{repeated.title} is already at {repeated.start_time.isoformat()}",
        )

    existing = await service.get_calendar_entry(context, data.calendar_entry_id)
    if existing is None:
        raise LookupError("Calendar entry not found")
    duration = (
        existing.end_time - existing.start_time
        if existing.end_time is not None
        else timedelta(hours=1)
    )
    if data.new_start_time is not None:
        resolved_start_time = data.new_start_time
    else:
        local_start = existing.start_time.astimezone(ZoneInfo(existing.timezone))
        resolved_start_time = datetime.combine(
            data.new_date,
            local_start.time(),
            tzinfo=ZoneInfo(existing.timezone),
        )
    new_end_time = resolved_start_time + duration
    conflicts = await service.list_calendar_conflicts(
        context,
        start_time=resolved_start_time,
        end_time=new_end_time,
        default_duration=timedelta(hours=1),
        exclude_entry_id=existing.id,
    )
    updated = await service.reschedule_calendar_entry(
        context,
        entry_id=existing.id,
        start_time=resolved_start_time,
        end_time=new_end_time,
        expected_updated_at=data.expected_updated_at,
        updated_by_run_id=updated_by_run_id,
    )
    if updated is None:
        raise CalendarEntryChangedError(
            "Calendar entry changed after it was selected; search again before updating"
        )
    return CalendarEntryRescheduleResult(
        calendar_entry_id=updated.id,
        previous_start_time=existing.start_time,
        previous_end_time=existing.end_time,
        calendar_entry=updated,
        conflicts=list(conflicts),
        summary=(
            f"Moved {updated.title} from {existing.start_time.isoformat()} "
            f"to {updated.start_time.isoformat()} with {len(conflicts)} conflict(s)"
        ),
    )


async def check_calendar_conflicts(
    session: AsyncSession,
    context: TenantContext,
    *,
    start_time: datetime,
    end_time: datetime | None = None,
) -> CalendarConflictResult:
    resolved_end = end_time or start_time + timedelta(hours=1)
    conflicts = await SchedulingService(session).list_calendar_conflicts(
        context,
        start_time=start_time,
        end_time=resolved_end,
        default_duration=timedelta(hours=1),
    )
    return CalendarConflictResult(
        requested_start_time=start_time,
        requested_end_time=resolved_end,
        conflicts=list(conflicts),
        summary=(
            "The requested time overlaps an existing calendar entry."
            if conflicts
            else "No calendar conflicts found."
        ),
        requires_follow_up=bool(conflicts),
    )


async def cancel_calendar_entry(
    session: AsyncSession,
    context: TenantContext,
    data: CancelCalendarEntryInput,
    *,
    cancelled_by_run_id: UUID,
) -> CalendarEntryCancellationResult:
    service = SchedulingService(session)
    repeated = await service.get_calendar_entry_cancelled_by_run(
        context, cancelled_by_run_id
    )
    if repeated is not None:
        return CalendarEntryCancellationResult(
            calendar_entry_id=repeated.id,
            calendar_entry=repeated,
            summary=f"{repeated.title} is already cancelled",
        )

    existing = await service.get_calendar_entry_including_cancelled(
        context, data.calendar_entry_id
    )
    if existing is None:
        raise LookupError("Calendar entry not found")
    if existing.cancelled_at is not None:
        return CalendarEntryCancellationResult(
            calendar_entry_id=existing.id,
            calendar_entry=existing,
            summary=f"{existing.title} is already cancelled",
        )
    cancelled = await service.cancel_calendar_entry(
        context,
        entry_id=existing.id,
        expected_updated_at=data.expected_updated_at,
        cancelled_by_run_id=cancelled_by_run_id,
        cancellation_reason=data.reason,
    )
    if cancelled is None:
        current = await service.get_calendar_entry_including_cancelled(
            context, existing.id
        )
        if current is not None and current.cancelled_at is not None:
            return CalendarEntryCancellationResult(
                calendar_entry_id=current.id,
                calendar_entry=current,
                summary=f"{current.title} is already cancelled",
            )
        raise CalendarEntryChangedError(
            "Calendar entry changed after it was selected; search again before cancelling"
        )
    return CalendarEntryCancellationResult(
        calendar_entry_id=cancelled.id,
        calendar_entry=cancelled,
        summary=f"Cancelled {cancelled.title} at {cancelled.start_time.isoformat()}",
    )


async def create_task_item(
    session: AsyncSession,
    context: TenantContext,
    data: CreateTaskItemInput,
    *,
    created_by_run_id: UUID | None = None,
    operation_key: str | None = None,
) -> TaskItemToolResult:
    service = SchedulingService(session)
    if created_by_run_id is not None:
        existing = await service.get_task_item_created_by_run(
            context, created_by_run_id, operation_key
        )
        if existing is not None:
            return TaskItemToolResult(
                task_item_id=existing.id,
                summary=(
                    existing.title
                    if existing.due_at is None
                    else f"{existing.title} due {existing.due_at.isoformat()}"
                ),
                task_item=existing,
            )
    task = await service.create_task_item(
        context,
        TaskItemCreate(
            **data.model_dump(),
            created_by_run_id=created_by_run_id,
            created_operation_key=operation_key,
        ),
    )
    return TaskItemToolResult(
        task_item_id=task.id,
        summary=task.title if task.due_at is None else f"{task.title} due {task.due_at.isoformat()}",
        task_item=task,
    )


async def list_task_items(
    session: AsyncSession,
    context: TenantContext,
) -> list[TaskItem]:
    service = SchedulingService(session)
    return list(await service.list_task_items(context))


async def search_task_items(
    session: AsyncSession,
    context: TenantContext,
    data: SearchTaskItemsInput,
) -> list[TaskItem]:
    return list(
        await SchedulingService(session).search_task_items(
            context, title_query=data.title_query, status=data.status
        )
    )


async def update_task_item(
    session: AsyncSession,
    context: TenantContext,
    data: UpdateTaskItemInput,
    *,
    updated_by_run_id: UUID,
    operation_key: str,
) -> TaskItemUpdateResult:
    service = SchedulingService(session)
    repeated = await service.get_task_item_updated_by_operation(
        context, updated_by_run_id, operation_key
    )
    if repeated is not None:
        return TaskItemUpdateResult(
            task_item_id=repeated.id,
            previous_task_item=repeated,
            task_item=repeated,
            summary=f"{repeated.title} was already updated",
        )

    existing = await service.get_task_item(context, data.task_item_id)
    if existing is None:
        raise LookupError("Task item not found")
    updated = await service.update_task_item(
        context,
        task_id=existing.id,
        expected_updated_at=data.expected_updated_at,
        data=TaskItemUpdate(
            title=data.new_title,
            due_at=data.new_due_at,
            status=data.new_status,
            updated_by_run_id=updated_by_run_id,
            updated_operation_key=operation_key,
        ),
    )
    if updated is None:
        raise TaskItemChangedError(
            "Task item changed after it was selected; search again before updating"
        )
    return TaskItemUpdateResult(
        task_item_id=updated.id,
        previous_task_item=existing,
        task_item=updated,
        summary=f"Updated {updated.title} ({updated.status.value})",
    )
