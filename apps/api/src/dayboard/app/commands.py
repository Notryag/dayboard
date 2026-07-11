from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends
from langchain_core.messages import HumanMessage, ToolMessage
from north import CompactionEvent, RuntimeUsageAccumulator, invoke_agent_once
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
from dayboard.db.session import SessionLocal, get_session
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
        usage_session_factory=SessionLocal,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)
        self.invoker = invoker
        self.checkpointer = checkpointer
        self.conversations = conversation_service or ConversationService(session)
        self.usage_session_factory = usage_session_factory

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
        conversation_message: str | None = None,
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
            content=conversation_message or request.message,
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
        usage_accumulator = RuntimeUsageAccumulator()
        try:
            if status == AgentRunStatus.queued:
                if not await runs.mark_running(context, run):
                    return
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
                await usage_accumulator(event)
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

            clarification_question = _extract_clarification_question(result)
            if clarification_question:
                pending = await self.conversations.set_pending_clarification(
                    context,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    question=clarification_question,
                    state_data=_extract_clarification_state_data(result),
                )
                if not await runs.mark_needs_clarification(
                    context,
                    run,
                    question=clarification_question,
                    event_metadata={
                        "state_version": pending.version,
                        "interaction": pending.state_data.get("interaction"),
                    },
                ):
                    await self.session.rollback()
                    return
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
            if not await runs.mark_completed(
                context,
                run,
                result_message=message,
                event_metadata={"runtime": "north"},
            ):
                await self.session.rollback()
                return
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
        finally:
            await self._settle_provider_usage(context, run_id, usage_accumulator)

    async def _settle_provider_usage(
        self,
        context: TenantContext,
        run_id: UUID,
        usage_accumulator: RuntimeUsageAccumulator,
    ) -> None:
        usage = usage_accumulator.total
        if usage is None:
            return
        provider, _, _ = self.settings.agent_model_name.partition(":")
        try:
            async with self.usage_session_factory() as usage_session:
                await ProviderUsageRepository(usage_session).settle(
                    context,
                    run_id=run_id,
                    provider=provider or "unknown",
                    model=self.settings.agent_model_name,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    usage_metadata={"calls": usage_accumulator.calls},
                )
                await usage_session.commit()
            logger.info(
                "dayboard.command.provider_usage_settled",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
        except Exception:
            logger.exception(
                "dayboard.command.provider_usage_settlement_failed",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
            )

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
        transitioned = await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        if not transitioned:
            await self.session.rollback()
            return
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
        transitioned = await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        if not transitioned:
            await session.rollback()
            return
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


def _extract_clarification_state_data(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}

    state_data: dict[str, Any] = {}
    thread_data = result.get("thread_data")
    clarification = thread_data.get("clarification") if isinstance(thread_data, dict) else None
    if isinstance(clarification, dict) and clarification.get("response_kind") == "single_choice":
        options = clarification.get("options")
        if isinstance(options, list):
            choices = [
                {"key": f"candidate_{index}", "value": option, "label": option}
                for index, option in enumerate(
                    (option for option in options[:10] if isinstance(option, str) and option.strip()),
                    start=1,
                )
            ]
            if choices:
                state_data = {
                    "candidates": choices,
                    "interaction": {
                        "type": "suggested_choice",
                        "options": [
                            {"key": choice["key"], "label": choice["label"]}
                            for choice in choices
                        ],
                    },
                }

    if not isinstance(result.get("messages"), list):
        return state_data

    search_calls: dict[str, dict[str, Any]] = {}
    latest: tuple[dict[str, Any], Any] | None = None
    for message in result["messages"]:
        tool_calls = getattr(message, "tool_calls", None)
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls", tool_calls)
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict) or call.get("name") != "search_calendar_entries":
                    continue
                call_id = call.get("id")
                args = call.get("args")
                if isinstance(call_id, str) and isinstance(args, dict):
                    search_calls[call_id] = args

        if isinstance(message, ToolMessage):
            call_id = message.tool_call_id
            content = message.content
        elif isinstance(message, dict) and message.get("type") == "tool":
            call_id = message.get("tool_call_id")
            content = message.get("content")
        else:
            continue
        if isinstance(call_id, str) and call_id in search_calls:
            latest = (search_calls[call_id], content)

    if latest is None:
        return state_data
    args, content = latest
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return state_data
    if not isinstance(content, list):
        return state_data

    allowed = ("id", "title", "start_time", "end_time", "timezone", "updated_at")
    candidates = [
        {"key": f"candidate_{index}", **{key: item[key] for key in allowed if key in item}}
        for index, item in enumerate(
            (item for item in content[:10] if isinstance(item, dict)), start=1
        )
    ]
    calendar_state_data: dict[str, Any] = {
        "intent": args.get("purpose", "view"),
        "candidates": candidates,
    }
    if candidates:
        calendar_state_data["interaction"] = {
            "type": "calendar_entry_choice",
            "options": [
                {
                    key: candidate[key]
                    for key in ("key", "title", "start_time", "end_time", "timezone")
                    if key in candidate
                }
                for candidate in candidates
            ],
        }
    return calendar_state_data


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
