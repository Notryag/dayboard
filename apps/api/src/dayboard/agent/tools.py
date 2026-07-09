from __future__ import annotations

from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.domain.calendar import Reminder
from dayboard.domain.tasks import TaskStatus
from dayboard.tools import (
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    create_calendar_entry,
    create_task_item,
    list_calendar_entries,
    list_task_items,
)


class ListCalendarEntriesInput(BaseModel):
    pass


class ListTaskItemsInput(BaseModel):
    pass


class AgentCreateCalendarEntryInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    start_time: str = Field(description="ISO 8601 datetime with timezone offset.")
    end_time: str | None = Field(default=None, description="Optional ISO 8601 datetime.")
    timezone: str = Field(min_length=1, max_length=64)
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = None


class AgentCreateTaskItemInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    due_at: str | None = Field(default=None, description="Optional ISO 8601 datetime.")
    timezone: str = Field(min_length=1, max_length=64)
    reminder: Reminder | None = None
    status: TaskStatus = TaskStatus.open


def build_scheduling_tools(
    *,
    session: AsyncSession,
    context: TenantContext,
    run_id: UUID | None,
) -> list[StructuredTool]:
    """Build agent-safe scheduling tools with trusted context injected.

    The model only sees product fields. Database session, tenant/user context,
    and run identity stay server-owned and are captured by these closures.
    """

    async def agent_create_calendar_entry(**kwargs):
        input_data = AgentCreateCalendarEntryInput.model_validate(kwargs)
        data = CreateCalendarEntryInput.model_validate(input_data.model_dump())
        result = await create_calendar_entry(
            session,
            context,
            data,
            created_by_run_id=run_id,
        )
        return result.model_dump(mode="json")

    async def agent_list_calendar_entries():
        entries = await list_calendar_entries(session, context)
        return [entry.model_dump(mode="json") for entry in entries]

    async def agent_create_task_item(**kwargs):
        input_data = AgentCreateTaskItemInput.model_validate(kwargs)
        data = CreateTaskItemInput.model_validate(input_data.model_dump())
        result = await create_task_item(
            session,
            context,
            data,
            created_by_run_id=run_id,
        )
        return result.model_dump(mode="json")

    async def agent_list_task_items():
        tasks = await list_task_items(session, context)
        return [task.model_dump(mode="json") for task in tasks]

    return [
        StructuredTool.from_function(
            coroutine=agent_create_calendar_entry,
            name="create_calendar_entry",
            description="Create a Dayboard calendar entry when title and start time are known.",
            args_schema=AgentCreateCalendarEntryInput,
        ),
        StructuredTool.from_function(
            coroutine=agent_list_calendar_entries,
            name="list_calendar_entries",
            description="List active Dayboard calendar entries for the current user.",
            args_schema=ListCalendarEntriesInput,
        ),
        StructuredTool.from_function(
            coroutine=agent_create_task_item,
            name="create_task_item",
            description="Create a Dayboard task item when the user asks to track work without a scheduled start time.",
            args_schema=AgentCreateTaskItemInput,
        ),
        StructuredTool.from_function(
            coroutine=agent_list_task_items,
            name="list_task_items",
            description="List active Dayboard task items for the current user.",
            args_schema=ListTaskItemsInput,
        ),
    ]
