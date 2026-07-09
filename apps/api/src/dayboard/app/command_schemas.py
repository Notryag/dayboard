from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from dayboard.tools import (
    CalendarEntryToolResult,
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    TaskItemToolResult,
)

CommandIntent = Literal["calendar_entry", "task_item"]
CommandStatus = Literal["completed", "needs_clarification"]


class CommandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    intent: CommandIntent | None = None
    calendar_entry: CreateCalendarEntryInput | None = None
    task_item: CreateTaskItemInput | None = None


class CommandResponse(BaseModel):
    run_id: str
    status: CommandStatus
    message: str
    result: CalendarEntryToolResult | TaskItemToolResult | None = None
    clarification_question: str | None = None
