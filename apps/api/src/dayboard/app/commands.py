from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends
from langchain_core.messages import HumanMessage
from north import invoke_agent_once
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.agent.factory import build_dayboard_agent
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.runs import AgentRunService
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext
from dayboard.db.provider_usage_repository import ProviderUsageRepository
from dayboard.db.session import get_session
from dayboard.domain.runs import AgentRunStatus

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

    async def create_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> UUID:
        run = await AgentRunService(self.session).create_run(
            context,
            input_message=request.message,
        )
        await self.session.commit()
        logger.info(
            "dayboard.command.run_queued",
            run_id=str(run.id),
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
        )
        return run.id

    async def execute_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
        run_id: UUID,
    ) -> None:
        runs = AgentRunService(self.session)
        run = await runs.get_run_row(context, run_id)
        if run is None:
            raise LookupError(f"Run {run_id} not found")
        status = AgentRunStatus(run.status)
        if status in {
            AgentRunStatus.completed,
            AgentRunStatus.failed,
            AgentRunStatus.cancelled,
            AgentRunStatus.needs_clarification,
        }:
            return
        try:
            if status == AgentRunStatus.queued:
                await runs.mark_running(context, run)
                await self.session.commit()
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

            usage = _extract_provider_usage(result)
            if usage is not None:
                provider, _, _ = self.settings.agent_model_name.partition(":")
                await ProviderUsageRepository(self.session).create(
                    context,
                    run_id=run.id,
                    provider=provider or "unknown",
                    model=self.settings.agent_model_name,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    total_tokens=usage["total_tokens"],
                    usage_metadata={"calls": usage["calls"]},
                )
                logger.info(
                    "dayboard.command.provider_usage_recorded",
                    run_id=str(run.id),
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                    model=self.settings.agent_model_name,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    total_tokens=usage["total_tokens"],
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
                return

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

    async def fail_command_run(
        self,
        context: TenantContext,
        run_id: UUID,
        exc: Exception,
    ) -> None:
        runs = AgentRunService(self.session)
        run = await runs.get_run_row(context, run_id)
        if run is None:
            raise LookupError(f"Run {run_id} not found")
        await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        await self.session.commit()


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


def _extract_provider_usage(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict) or not isinstance(result.get("messages"), list):
        return None

    calls: list[dict[str, int]] = []
    for message in result["messages"]:
        metadata = getattr(message, "usage_metadata", None)
        if metadata is None and isinstance(message, dict):
            metadata = message.get("usage_metadata")
        if not isinstance(metadata, dict):
            continue

        input_tokens = _non_negative_int(metadata.get("input_tokens"))
        output_tokens = _non_negative_int(metadata.get("output_tokens"))
        total_tokens = _non_negative_int(metadata.get("total_tokens"))
        if input_tokens is None and output_tokens is None and total_tokens is None:
            continue
        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0
        calls.append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens if total_tokens is not None else input_tokens + output_tokens,
            }
        )

    if not calls:
        return None
    return {
        "input_tokens": sum(call["input_tokens"] for call in calls),
        "output_tokens": sum(call["output_tokens"] for call in calls),
        "total_tokens": sum(call["total_tokens"] for call in calls),
        "calls": calls,
    }


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
