from __future__ import annotations

from typing import Any

from fastapi import Depends
from langchain_core.messages import HumanMessage
from north import invoke_agent_once
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.agent.factory import build_dayboard_agent
from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.app.runs import AgentRunService
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext
from dayboard.db.session import get_session

logger = structlog.get_logger(__name__)


def get_command_service(session: AsyncSession = Depends(get_session)) -> CommandService:
    return CommandService(session)


class CommandService:
    """Dayboard command application service backed directly by north."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        budget_guard: ProviderBudgetGuard | None = None,
        invoker=invoke_agent_once,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)
        self.invoker = invoker

    async def handle_command(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        runs = AgentRunService(self.session)
        run = None
        try:
            run = await runs.create_run(context, input_message=request.message)
            await runs.mark_running(context, run)
            logger.info(
                "dayboard.command.run_started",
                run_id=str(run.id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                message_length=len(request.message),
            )

            estimate = self.budget_guard.estimate(input_text=request.message)
            logger.info(
                "dayboard.command.budget_check_started",
                run_id=str(run.id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                estimated_tokens=estimate.token_units,
                request_units=estimate.request_units,
            )
            self.budget_guard.check(
                context=context,
                model_name=self.settings.agent_model_name,
                estimate=estimate,
            )

            logger.info(
                "dayboard.command.north_invoke_started",
                run_id=str(run.id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
            )
            result = await self.invoker(
                agent_factory=lambda: build_dayboard_agent(
                    self.settings,
                    session=self.session,
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
                await self.session.commit()
                logger.info(
                    "dayboard.command.needs_clarification",
                    run_id=str(run.id),
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                )
                return CommandResponse(
                    run_id=str(run.id),
                    status="needs_clarification",
                    message="More scheduling details are needed.",
                    clarification_question=clarification_question,
                )

            message = _extract_final_message(result)
            await runs.mark_completed(
                context,
                run,
                result_message=message,
                event_metadata={"runtime": "north"},
            )
            await self.session.commit()
            logger.info(
                "dayboard.command.completed",
                run_id=str(run.id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                result_length=len(message),
            )
            return CommandResponse(run_id=str(run.id), status="completed", message=message)
        except Exception as exc:
            if run is not None:
                await _mark_run_failed(runs, self.session, context, run, exc)
            logger.exception(
                "dayboard.command.failed",
                run_id=str(run.id) if run is not None else None,
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                error_type=type(exc).__name__,
            )
            raise


async def _mark_run_failed(
    runs: AgentRunService,
    session: AsyncSession,
    context: TenantContext,
    run: Any,
    exc: Exception,
) -> None:
    try:
        await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        await session.commit()
    except Exception:
        logger.exception(
            "dayboard.command.failed_status_update_failed",
            run_id=str(run.id),
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
        )


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip() or type(exc).__name__
    return message[:4000]


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
