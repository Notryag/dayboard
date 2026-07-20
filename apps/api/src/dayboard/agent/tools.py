from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, time, timedelta
import asyncio
from hashlib import sha256
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.tools import StructuredTool
from pydantic import AwareDatetime, BaseModel, Field, NaiveDatetime, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.domain.calendar import Reminder
from dayboard.domain.tasks import TaskStatus
from dayboard.timezones import resolve_local_datetime
from dayboard.tools import (
    CancelCalendarEntryInput,
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    RescheduleCalendarEntryInput,
    SearchCalendarEntriesInput,
    SearchTaskItemsInput,
    UpdateTaskItemInput,
    cancel_calendar_entry,
    create_calendar_entry,
    create_task_item,
    reschedule_calendar_entry,
    search_calendar_entries,
    search_task_items,
    update_task_item,
)


class AgentCreateCalendarEntryInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    local_start: NaiveDatetime = Field(
        description="Local ISO 8601 datetime without an offset."
    )
    local_end: NaiveDatetime | None = Field(
        default=None,
        description="Optional local ISO 8601 datetime without an offset.",
    )
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = Field(
        default_factory=lambda: Reminder(offset="PT0M", anchor="start_time"),
        description=(
            "Defaults to PT0M at start; use an explicit advance offset or null for no reminder."
        ),
    )


class AgentCreateTaskItemInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)


class AgentSearchCalendarEntriesInput(BaseModel):
    local_start: NaiveDatetime | None = Field(
        default=None,
        description="Optional inclusive local interval start without an offset.",
    )
    local_end: NaiveDatetime | None = Field(
        default=None,
        description="Optional exclusive local interval end without an offset.",
    )
    title_query: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_date_window(self) -> AgentSearchCalendarEntriesInput:
        if (self.local_start is None) != (self.local_end is None):
            raise ValueError("local_start and local_end must be provided together")
        if (
            self.local_start is not None
            and self.local_end is not None
            and self.local_start >= self.local_end
        ):
            raise ValueError("local_start must be before local_end")
        return self


class AgentRescheduleCalendarEntryInput(BaseModel):
    calendar_entry_id: UUID
    new_date: date | None = None
    new_local_start: NaiveDatetime | None = None
    new_local_end: NaiveDatetime | None = None
    expected_updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_target(self) -> AgentRescheduleCalendarEntryInput:
        if self.new_date is not None and self.new_local_start is not None:
            raise ValueError("new_date and new_local_start cannot be combined")
        if (
            self.new_date is None
            and self.new_local_start is None
            and self.new_local_end is None
        ):
            raise ValueError("provide at least one calendar time change")
        return self


class AgentUpdateTaskItemInput(BaseModel):
    task_item_id: UUID
    expected_updated_at: AwareDatetime
    new_title: str | None = Field(default=None, min_length=1, max_length=240)
    new_status: TaskStatus | None = None

    @model_validator(mode="after")
    def validate_change(self) -> AgentUpdateTaskItemInput:
        if self.new_title is None and self.new_status is None:
            raise ValueError("provide at least one task change")
        return self


def _calendar_entry_view(entry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "title": entry.title,
        "start_time": entry.start_time.isoformat(),
        "end_time": entry.end_time.isoformat() if entry.end_time else None,
        "timezone": entry.timezone,
        "participants": entry.participants,
        "reminder": entry.reminder.model_dump() if entry.reminder else None,
        "status": (
            "cancelled"
            if entry.cancelled_at is not None
            else "completed"
            if entry.completed_at is not None
            else "scheduled"
        ),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def _task_item_view(task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "timezone": task.timezone,
        "reminder": task.reminder.model_dump() if task.reminder else None,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _create_operation_key(kind: str, data: BaseModel) -> str:
    identity = f"{kind}:{data.model_dump_json()}"
    return sha256(identity.encode("utf-8")).hexdigest()


def build_scheduling_tools(
    *,
    session: AsyncSession,
    context: TenantContext,
    run_id: UUID | None,
    progress: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None,
) -> list[StructuredTool]:
    """Build agent-safe scheduling tools with trusted context injected.

    The model only sees product fields. Database session, tenant/user context,
    and run identity stay server-owned and are captured by these closures.
    """
    tool_lock = asyncio.Lock()

    def serialize_tool(function):
        async def serialized(**kwargs):
            async with tool_lock:
                return await function(**kwargs)

        return serialized

    async def agent_create_calendar_entry(**kwargs):
        input_data = AgentCreateCalendarEntryInput.model_validate(kwargs)
        data = CreateCalendarEntryInput(
            title=input_data.title,
            start_time=resolve_local_datetime(input_data.local_start, context.timezone),
            end_time=(
                resolve_local_datetime(input_data.local_end, context.timezone)
                if input_data.local_end
                else None
            ),
            timezone=context.timezone,
            participants=input_data.participants,
            reminder=input_data.reminder,
        )
        result = await create_calendar_entry(
            session,
            context,
            data,
            created_by_run_id=run_id,
            operation_key=_create_operation_key("calendar_entry", input_data),
        )
        await session.commit()
        return {
            "type": result.type,
            "calendar_entry": _calendar_entry_view(result.calendar_entry),
            "conflicts": [_calendar_entry_view(entry) for entry in result.conflicts],
        }

    async def agent_search_calendar_entries(**kwargs):
        input_data = AgentSearchCalendarEntriesInput.model_validate(kwargs)
        if input_data.local_start is None:
            local_today = datetime.now(ZoneInfo(context.timezone)).date()
            local_start = datetime.combine(local_today, time.min)
            local_end = local_start + timedelta(days=90)
        else:
            local_start = input_data.local_start
            local_end = input_data.local_end
        assert local_end is not None
        start_time = resolve_local_datetime(local_start, context.timezone)
        end_time = resolve_local_datetime(local_end, context.timezone)
        entries = await search_calendar_entries(
            session,
            context,
            SearchCalendarEntriesInput(
                start_time=start_time,
                end_time=end_time,
                title_query=input_data.title_query,
            ),
        )
        return [_calendar_entry_view(entry) for entry in entries]

    async def agent_reschedule_calendar_entry(**kwargs):
        if run_id is None:
            raise RuntimeError("Rescheduling requires a run id")
        input_data = AgentRescheduleCalendarEntryInput.model_validate(kwargs)
        data = RescheduleCalendarEntryInput(
            calendar_entry_id=input_data.calendar_entry_id,
            new_date=input_data.new_date,
            new_start_time=(
                resolve_local_datetime(input_data.new_local_start, context.timezone)
                if input_data.new_local_start
                else None
            ),
            new_end_time=(
                resolve_local_datetime(input_data.new_local_end, context.timezone)
                if input_data.new_local_end
                else None
            ),
            expected_updated_at=input_data.expected_updated_at,
        )
        result = await reschedule_calendar_entry(
            session,
            context,
            data,
            updated_by_run_id=run_id,
            operation_key=_create_operation_key("calendar_entry_reschedule", input_data),
        )
        await session.commit()
        return {
            "type": result.type,
            "previous_start_time": result.previous_start_time.isoformat(),
            "previous_end_time": (
                result.previous_end_time.isoformat() if result.previous_end_time else None
            ),
            "calendar_entry": _calendar_entry_view(result.calendar_entry),
            "conflicts": [_calendar_entry_view(entry) for entry in result.conflicts],
        }

    async def agent_cancel_calendar_entry(**kwargs):
        if run_id is None:
            raise RuntimeError("Cancelling requires a run id")
        input_data = CancelCalendarEntryInput.model_validate(kwargs)
        result = await cancel_calendar_entry(
            session,
            context,
            input_data,
            cancelled_by_run_id=run_id,
            operation_key=_create_operation_key("calendar_entry_cancel", input_data),
        )
        await session.commit()
        return {
            "type": result.type,
            "calendar_entry": _calendar_entry_view(result.calendar_entry),
        }

    async def agent_create_task_item(**kwargs):
        input_data = AgentCreateTaskItemInput.model_validate(kwargs)
        data = CreateTaskItemInput(
            title=input_data.title,
            timezone=context.timezone,
        )
        result = await create_task_item(
            session,
            context,
            data,
            created_by_run_id=run_id,
            operation_key=_create_operation_key("task_item", input_data),
        )
        await session.commit()
        return {
            "type": result.type,
            "task_item": _task_item_view(result.task_item),
        }

    async def agent_search_task_items(**kwargs):
        input_data = SearchTaskItemsInput.model_validate(kwargs)
        tasks = await search_task_items(session, context, input_data)
        return [_task_item_view(task) for task in tasks]

    async def agent_update_task_item(**kwargs):
        if run_id is None:
            raise RuntimeError("Updating a task requires a run id")
        input_data = AgentUpdateTaskItemInput.model_validate(kwargs)
        data = UpdateTaskItemInput(
            task_item_id=input_data.task_item_id,
            expected_updated_at=input_data.expected_updated_at,
            new_title=input_data.new_title,
            new_status=input_data.new_status,
        )
        result = await update_task_item(
            session,
            context,
            data,
            updated_by_run_id=run_id,
            operation_key=_create_operation_key("task_item_update", input_data),
        )
        await session.commit()
        return {
            "type": result.type,
            "task_item": _task_item_view(result.task_item),
        }

    return [
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_create_calendar_entry),
            name="create_calendar_entry",
            description=(
                "Create a calendar entry for an activity at a concrete local start time."
            ),
            args_schema=AgentCreateCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_search_calendar_entries),
            name="search_calendar_entries",
            description=(
                "List or search calendar entries overlapping an optional local interval."
            ),
            args_schema=AgentSearchCalendarEntriesInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_reschedule_calendar_entry),
            name="reschedule_calendar_entry",
            description=(
                "Change one identified calendar entry's local date, start, and/or end time."
            ),
            args_schema=AgentRescheduleCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_cancel_calendar_entry),
            name="cancel_calendar_entry",
            description="Cancel one identified calendar entry.",
            args_schema=CancelCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_create_task_item),
            name="create_task_item",
            description=(
                "Create an action with no resolvable date or time."
            ),
            args_schema=AgentCreateTaskItemInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_search_task_items),
            name="search_task_items",
            description=(
                "Search tasks by title and status before changing one."
            ),
            args_schema=SearchTaskItemsInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_update_task_item),
            name="update_task_item",
            description=(
                "Update one identified task's title or status."
            ),
            args_schema=AgentUpdateTaskItemInput,
        ),
    ]
