from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import asyncio
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends
from langchain_core.messages import HumanMessage
from north import CompactionEvent, invoke_agent_once
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.agent.factory import build_dayboard_agent
from dayboard.agent.observability import project_runtime_event
from dayboard.app.conversations import ConversationService
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.runs import AgentRunService
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext
from dayboard.db.provider_usage_repository import ProviderUsageRepository
from dayboard.db.run_repositories import IdempotencyKeyRepository
from dayboard.db.session import get_session
from dayboard.domain.runs import AgentRunStatus
from dayboard.domain.conversations import ConversationRole

logger = structlog.get_logger(__name__)


class IdempotencyConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CommandRunCreation:
    run_id: UUID
    status: AgentRunStatus
    created: bool
    thread_id: UUID


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
        checkpointer=None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)
        self.invoker = invoker
        self.checkpointer = checkpointer
        self.conversations = conversation_service or ConversationService(session)

    async def create_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
        idempotency_key: str | None = None,
    ) -> UUID:
        result = await self.create_or_get_command_run(
            context,
            request,
            idempotency_key=idempotency_key,
        )
        return result.run_id

    async def create_or_get_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
        *,
        idempotency_key: str | None = None,
        thread_id: UUID | None = None,
    ) -> CommandRunCreation:
        run_id: UUID | None = None
        if idempotency_key is not None:
            request_identity = f"{thread_id or 'new'}:{request.model_dump_json()}"
            request_hash = sha256(request_identity.encode("utf-8")).hexdigest()
            record, claimed = await IdempotencyKeyRepository(self.session).claim(
                context,
                key=idempotency_key,
                request_hash=request_hash,
                run_id=uuid4(),
            )
            if not claimed:
                if record.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used for a different request"
                    )
                existing = await AgentRunService(self.session).get_run(context, record.run_id)
                if existing is None:
                    raise RuntimeError("Idempotency key references a missing run")
                return CommandRunCreation(existing.id, existing.status, False, existing.thread_id)
            run_id = record.run_id
        conversations = self.conversations
        if thread_id is None:
            thread = await conversations.create_thread(
                context,
                title=request.message[:80],
            )
            thread_id = thread.id
        else:
            await conversations.require_thread(context, thread_id)
        create_kwargs: dict[str, Any] = {
            "input_message": request.message,
            "thread_id": thread_id,
        }
        if run_id is not None:
            create_kwargs["run_id"] = run_id
        run = await AgentRunService(self.session).create_run(context, **create_kwargs)
        await conversations.append_message(
            context,
            thread_id=thread_id,
            run_id=run.id,
            role=ConversationRole.user,
            content=request.message,
        )
        await self.session.commit()
        logger.info(
            "dayboard.command.run_queued",
            run_id=str(run.id),
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
        )
        return CommandRunCreation(run.id, AgentRunStatus.queued, True, run.thread_id)

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

            async def record_progress(
                event_type: str,
                content: str,
                event_metadata: dict[str, Any],
            ) -> None:
                latest = await runs.get_run_row(context, run.id)
                if latest is not None and AgentRunStatus(latest.status) == AgentRunStatus.cancelled:
                    raise asyncio.CancelledError()
                await runs.append_progress(
                    context,
                    run.id,
                    event_type=event_type,
                    content=content,
                    event_metadata=event_metadata,
                )
                await self.session.commit()

            async def record_runtime_event(event) -> None:
                latest = await runs.get_run_row(context, run.id)
                if latest is not None and AgentRunStatus(latest.status) == AgentRunStatus.cancelled:
                    raise asyncio.CancelledError()
                projected = project_runtime_event(event)
                if projected is None:
                    return
                await runs.append_progress(
                    context,
                    run.id,
                    event_type=projected.event_type,
                    content=projected.content,
                    event_metadata=projected.metadata,
                    category=projected.category,
                )
                await self.session.commit()

            async def record_compaction(event: CompactionEvent) -> None:
                await self.conversations.update_summary(
                    context,
                    run.thread_id,
                    event.summary_text,
                )
                await self.session.commit()
                logger.info(
                    "dayboard.command.context_compacted",
                    run_id=str(run.id),
                    thread_id=str(run.thread_id),
                    summarized_message_count=len(event.summarized_messages),
                    preserved_message_count=len(event.preserved_messages),
                )

            result = await self.invoker(
                agent_factory=lambda: build_dayboard_agent(
                    self.settings,
                    session=self.session,
                    context=context,
                    run_id=run.id,
                    checkpointer=self.checkpointer,
                    compaction_hooks=[record_compaction],
                    progress=record_progress,
                ),
                graph_input={"messages": [HumanMessage(content=request.message)]},
                config={
                    "configurable": {
                        "thread_id": str(run.thread_id),
                        "checkpoint_ns": "dayboard",
                    }
                },
                context={
                    "tenant_id": str(context.tenant_id),
                    "user_id": str(context.user_id),
                    "run_id": str(run.id),
                },
                event_sink=record_runtime_event,
            )

            latest = await runs.get_run_row(context, run.id)
            if latest is not None and AgentRunStatus(latest.status) == AgentRunStatus.cancelled:
                return

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
                await self.conversations.set_pending_clarification(
                    context,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    question=clarification_question,
                )
                await self.conversations.append_message(
                    context,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    role=ConversationRole.assistant,
                    content=clarification_question,
                    message_metadata={"status": "needs_clarification"},
                )
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
            await self.conversations.append_message(
                context,
                thread_id=run.thread_id,
                run_id=run.id,
                role=ConversationRole.assistant,
                content=message,
                message_metadata={"status": "completed"},
            )
            await self.conversations.clear_pending(context, run.thread_id)
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
                await _mark_run_failed(
                    runs, self.conversations, self.session, context, run.id, exc
                )
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
        await self.conversations.append_message(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            role=ConversationRole.assistant,
            content=_safe_error_message(exc),
            message_metadata={"status": "failed"},
        )
        await self.session.commit()


async def _mark_run_failed(
    runs: AgentRunService,
    conversations: ConversationService,
    session: AsyncSession,
    context: TenantContext,
    run_id: UUID,
    exc: Exception,
) -> None:
    try:
        await session.rollback()
        run = await runs.get_run_row(context, run_id)
        if run is None:
            return
        await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        await conversations.append_message(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            role=ConversationRole.assistant,
            content=_safe_error_message(exc),
            message_metadata={"status": "failed"},
        )
        await session.commit()
    except Exception:
        logger.exception(
            "dayboard.command.failed_status_update_failed",
            run_id=str(run_id),
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
