from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.runs import AgentRunService
from dayboard.context import TenantContext
from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.tools import (
    create_calendar_entry,
    create_task_item,
)


class PlaceholderCommandExecutor:
    """Temporary command path used only before the north agent loop exists.

    M3 must replace this placeholder with north-driven command execution,
    persisted run state, and agent-owned clarification behavior. Do not add
    more natural-language interpretation here.
    """

    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        runs = AgentRunService(session)
        run = await runs.create_run(context, input_message=request.message)
        await runs.mark_running(context, run)

        if request.intent == "calendar_entry" and request.calendar_entry is not None:
            result = await create_calendar_entry(session, context, request.calendar_entry)
            await runs.mark_completed(
                context,
                run,
                result_message=result.summary,
                event_metadata={
                    "tool": "create_calendar_entry",
                    "calendar_entry_id": str(result.calendar_entry_id),
                },
            )
            await session.commit()
            return CommandResponse(
                run_id=str(run.id),
                status="completed",
                message=result.summary,
                result=result,
            )

        if request.intent == "task_item" and request.task_item is not None:
            result = await create_task_item(session, context, request.task_item)
            await runs.mark_completed(
                context,
                run,
                result_message=result.summary,
                event_metadata={
                    "tool": "create_task_item",
                    "task_item_id": str(result.task_item_id),
                },
            )
            await session.commit()
            return CommandResponse(
                run_id=str(run.id),
                status="completed",
                message=result.summary,
                result=result,
            )

        # Temporary M2 fallback. The final behavior should be produced by the
        # north agent clarification flow, not by hard-coded application text.
        question = "你想创建日程还是任务？请补充时间、标题等必要信息。"
        await runs.mark_needs_clarification(context, run, question=question)
        await session.commit()
        return CommandResponse(
            run_id=str(run.id),
            status="needs_clarification",
            message="I need structured scheduling details before creating anything.",
            clarification_question=question,
        )


class CommandService:
    def __init__(self, session: AsyncSession, executor=None) -> None:
        self.session = session
        self.executor = executor or PlaceholderCommandExecutor()

    async def handle_command(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        return await self.executor.execute(self.session, context, request)
