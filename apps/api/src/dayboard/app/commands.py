from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.tools import (
    CalendarEntryToolResult,
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    TaskItemToolResult,
    create_calendar_entry,
    create_task_item,
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


class CommandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def handle_command(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        run_id = f"run_{uuid4().hex}"

        if request.intent == "calendar_entry" and request.calendar_entry is not None:
            result = await create_calendar_entry(self.session, context, request.calendar_entry)
            return CommandResponse(
                run_id=run_id,
                status="completed",
                message=result.summary,
                result=result,
            )

        if request.intent == "task_item" and request.task_item is not None:
            result = await create_task_item(self.session, context, request.task_item)
            return CommandResponse(
                run_id=run_id,
                status="completed",
                message=result.summary,
                result=result,
            )

        return CommandResponse(
            run_id=run_id,
            status="needs_clarification",
            message="I need structured scheduling details before creating anything.",
            clarification_question="你想创建日程还是任务？请补充时间、标题等必要信息。",
        )
