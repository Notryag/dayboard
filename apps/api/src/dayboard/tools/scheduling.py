from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.scheduling import SchedulingService
from dayboard.context import TenantContext
from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, Reminder
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskStatus


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


async def create_calendar_entry(
    session: AsyncSession,
    context: TenantContext,
    data: CreateCalendarEntryInput,
    *,
    created_by_run_id: UUID | None = None,
) -> CalendarEntryToolResult:
    service = SchedulingService(session)
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


async def create_task_item(
    session: AsyncSession,
    context: TenantContext,
    data: CreateTaskItemInput,
    *,
    created_by_run_id: UUID | None = None,
) -> TaskItemToolResult:
    service = SchedulingService(session)
    task = await service.create_task_item(
        context,
        TaskItemCreate(**data.model_dump(), created_by_run_id=created_by_run_id),
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
