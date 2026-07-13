from __future__ import annotations

from collections.abc import Awaitable, Callable
import asyncio
from hashlib import sha256
from typing import Any
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import AwareDatetime, BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.domain.calendar import Reminder
from dayboard.domain.tasks import TaskStatus
from dayboard.tools import (
    CancelCalendarEntryInput,
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    RescheduleCalendarEntryInput,
    SearchCalendarEntriesInput,
    SearchTaskItemsInput,
    UpdateTaskItemInput,
    check_calendar_conflicts,
    cancel_calendar_entry,
    create_calendar_entry,
    create_task_item,
    list_calendar_entries,
    list_task_items,
    reschedule_calendar_entry,
    search_calendar_entries,
    search_task_items,
    update_task_item,
)


class ListCalendarEntriesInput(BaseModel):
    pass


class ListTaskItemsInput(BaseModel):
    pass


class CheckCalendarConflictsInput(BaseModel):
    start_time: AwareDatetime = Field(description="ISO 8601 datetime with timezone offset.")
    end_time: AwareDatetime | None = Field(
        default=None,
        description="Optional ISO 8601 datetime with timezone offset.",
    )


class AgentCreateCalendarEntryInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    start_time: AwareDatetime = Field(description="ISO 8601 datetime with timezone offset.")
    end_time: AwareDatetime | None = Field(
        default=None,
        description="Optional ISO 8601 datetime with timezone offset.",
    )
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = Field(
        default_factory=lambda: Reminder(offset="PT0M", anchor="start_time"),
        description=(
            "Defaults to PT0M at the event start. Use the user's explicit advance offset when "
            "provided, or null only when the user explicitly requests no reminder."
        ),
    )


class AgentCreateTaskItemInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    due_at: AwareDatetime | None = Field(
        default=None,
        description="Optional ISO 8601 datetime with timezone offset.",
    )
    reminder: Reminder | None = None
    status: TaskStatus = TaskStatus.open


def _calendar_entry_view(entry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "title": entry.title,
        "start_time": entry.start_time.isoformat(),
        "end_time": entry.end_time.isoformat() if entry.end_time else None,
        "timezone": entry.timezone,
        "updated_at": entry.updated_at.isoformat(),
    }


def _task_item_view(task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "timezone": task.timezone,
        "status": task.status.value,
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
        data = CreateCalendarEntryInput.model_validate(
            {**input_data.model_dump(), "timezone": context.timezone}
        )
        result = await create_calendar_entry(
            session,
            context,
            data,
            created_by_run_id=run_id,
            operation_key=_create_operation_key("calendar_entry", input_data),
        )
        return {
            "type": result.type,
            "calendar_entry_id": str(result.calendar_entry_id),
            "calendar_entry": _calendar_entry_view(result.calendar_entry),
            "conflicts": [_calendar_entry_view(entry) for entry in result.conflicts],
        }

    async def agent_check_calendar_conflicts(**kwargs):
        input_data = CheckCalendarConflictsInput.model_validate(kwargs)
        if progress:
            await progress(
                "conflict_check_started",
                "正在检查日程冲突",
                input_data.model_dump(),
            )
        result = await check_calendar_conflicts(
            session,
            context,
            start_time=input_data.start_time,
            end_time=input_data.end_time,
        )
        if progress:
            await progress(
                "conflict_check_completed",
                "发现日程冲突" if result.conflicts else "没有发现日程冲突",
                {"conflict_count": len(result.conflicts)},
            )
        return {
            "type": result.type,
            "requested_start_time": result.requested_start_time.isoformat(),
            "requested_end_time": result.requested_end_time.isoformat(),
            "conflicts": [_calendar_entry_view(entry) for entry in result.conflicts],
        }

    async def agent_list_calendar_entries():
        entries = await list_calendar_entries(session, context)
        return [_calendar_entry_view(entry) for entry in entries]

    async def agent_search_calendar_entries(**kwargs):
        input_data = SearchCalendarEntriesInput.model_validate(kwargs)
        entries = await search_calendar_entries(session, context, input_data)
        return [_calendar_entry_view(entry) for entry in entries]

    async def agent_reschedule_calendar_entry(**kwargs):
        if run_id is None:
            raise RuntimeError("Rescheduling requires a run id")
        input_data = RescheduleCalendarEntryInput.model_validate(kwargs)
        result = await reschedule_calendar_entry(
            session,
            context,
            input_data,
            updated_by_run_id=run_id,
            operation_key=_create_operation_key("calendar_entry_reschedule", input_data),
        )
        return {
            "type": result.type,
            "calendar_entry_id": str(result.calendar_entry_id),
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
        return {
            "type": result.type,
            "calendar_entry_id": str(result.calendar_entry_id),
            "calendar_entry": _calendar_entry_view(result.calendar_entry),
        }

    async def agent_create_task_item(**kwargs):
        input_data = AgentCreateTaskItemInput.model_validate(kwargs)
        data = CreateTaskItemInput.model_validate(
            {**input_data.model_dump(), "timezone": context.timezone}
        )
        result = await create_task_item(
            session,
            context,
            data,
            created_by_run_id=run_id,
            operation_key=_create_operation_key("task_item", input_data),
        )
        return {
            "type": result.type,
            "task_item_id": str(result.task_item_id),
            "task_item": _task_item_view(result.task_item),
        }

    async def agent_list_task_items():
        tasks = await list_task_items(session, context)
        return [_task_item_view(task) for task in tasks]

    async def agent_search_task_items(**kwargs):
        input_data = SearchTaskItemsInput.model_validate(kwargs)
        tasks = await search_task_items(session, context, input_data)
        return [_task_item_view(task) for task in tasks]

    async def agent_update_task_item(**kwargs):
        if run_id is None:
            raise RuntimeError("Updating a task requires a run id")
        input_data = UpdateTaskItemInput.model_validate(kwargs)
        result = await update_task_item(
            session,
            context,
            input_data,
            updated_by_run_id=run_id,
            operation_key=_create_operation_key("task_item_update", input_data),
        )
        return {
            "type": result.type,
            "task_item_id": str(result.task_item_id),
            "task_item": _task_item_view(result.task_item),
        }

    return [
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_check_calendar_conflicts),
            name="check_calendar_conflicts",
            description=(
                "Check whether a proposed calendar time overlaps existing entries. "
                "The end defaults to one hour after the start."
            ),
            args_schema=CheckCalendarConflictsInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_create_calendar_entry),
            name="create_calendar_entry",
            description=(
                "Create a Dayboard calendar entry when title and start time are known. Entries "
                "default to a PT0M reminder at their start; explicit advance offsets override it, "
                "and an explicit no-reminder request must pass null."
            ),
            args_schema=AgentCreateCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_list_calendar_entries),
            name="list_calendar_entries",
            description="List active Dayboard calendar entries for the current user.",
            args_schema=ListCalendarEntriesInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_search_calendar_entries),
            name="search_calendar_entries",
            description=(
                "Search the current user's calendar entries in a start-time range, "
                "optionally filtering by title. Use this to identify an entry before moving it."
            ),
            args_schema=SearchCalendarEntriesInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_reschedule_calendar_entry),
            name="reschedule_calendar_entry",
            description=(
                "Change one identified calendar entry's date, start time, and/or end time. "
                "An omitted start stays unchanged; changing only the date or start preserves "
                "the original duration unless new_end_time is supplied. "
                "Title, participants, reminder, and original timezone are always preserved."
            ),
            args_schema=RescheduleCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_cancel_calendar_entry),
            name="cancel_calendar_entry",
            description=(
                "Cancel one identified calendar entry. The entry is retained for audit, "
                "but disappears from active calendar queries."
            ),
            args_schema=CancelCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_create_task_item),
            name="create_task_item",
            description="Create a Dayboard task item when the user asks to track work without a scheduled start time.",
            args_schema=AgentCreateTaskItemInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_list_task_items),
            name="list_task_items",
            description="List active Dayboard task items for the current user.",
            args_schema=ListTaskItemsInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_search_task_items),
            name="search_task_items",
            description=(
                "Search the current user's tasks by title and status before changing, "
                "completing, or cancelling one."
            ),
            args_schema=SearchTaskItemsInput,
        ),
        StructuredTool.from_function(
            coroutine=serialize_tool(agent_update_task_item),
            name="update_task_item",
            description=(
                "Update one identified task's title, due time, or status. Use status "
                "completed when work is done and cancelled when the user drops it."
            ),
            args_schema=UpdateTaskItemInput,
        ),
    ]
