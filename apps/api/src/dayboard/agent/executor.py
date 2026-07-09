from __future__ import annotations

from typing import Protocol
from typing import Any

from langchain_core.messages import HumanMessage
from north import invoke_agent_once
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.agent.factory import build_dayboard_agent
from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.runs import AgentRunService
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext


class CommandExecutor(Protocol):
    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        """Execute a command and return the user-facing result."""


class NorthCommandExecutor:
    """North-backed command executor with Dayboard-owned persistence."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        budget_guard: ProviderBudgetGuard | None = None,
        invoker=invoke_agent_once,
    ) -> None:
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)
        self.invoker = invoker

    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        runs = AgentRunService(session)
        run = await runs.create_run(context, input_message=request.message)
        await runs.mark_running(context, run)

        estimate = self.budget_guard.estimate(input_text=request.message)
        self.budget_guard.check(
            context=context,
            model_name=self.settings.agent_model_name,
            estimate=estimate,
        )

        result = await self.invoker(
            agent_factory=lambda: build_dayboard_agent(
                self.settings,
                session=session,
                context=context,
                run_id=run.id,
            ),
            graph_input={"messages": [HumanMessage(content=request.message)]},
            config={"configurable": {"thread_id": str(run.id)}},
            context={
                "tenant_id": str(context.tenant_id),
                "user_id": str(context.user_id),
                "run_id": str(run.id),
            },
        )

        clarification_question = _extract_clarification_question(result)
        if clarification_question:
            await runs.mark_needs_clarification(context, run, question=clarification_question)
            await session.commit()
            return CommandResponse(
                run_id=str(run.id),
                status="needs_clarification",
                message="More scheduling details are needed.",
                clarification_question=clarification_question,
            )

        message = _extract_final_message(result)
        await runs.mark_completed(context, run, result_message=message, event_metadata={"executor": "north"})
        await session.commit()
        return CommandResponse(run_id=str(run.id), status="completed", message=message)


def _extract_clarification_question(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    thread_data = result.get("thread_data")
    if not isinstance(thread_data, dict):
        return None
    clarification = thread_data.get("clarification")
    if not isinstance(clarification, dict):
        return None
    question = clarification.get("question")
    return question if isinstance(question, str) and question else None


def _extract_final_message(result: Any) -> str:
    if not isinstance(result, dict):
        return "Done."

    messages = result.get("messages")
    if not isinstance(messages, list) or not messages:
        return "Done."

    for message in reversed(messages):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(message, dict):
            dict_content = message.get("content")
            if isinstance(dict_content, str) and dict_content.strip():
                return dict_content.strip()
    return "Done."
