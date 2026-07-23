from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends
from langchain_core.messages import HumanMessage, ToolMessage
from north import (
    CompactionEvent,
    RunExecutor,
    RunLifecycleHooks,
    RuntimeStreamEvent,
    RuntimeUsageAccumulator,
)
from north.runtime import MemoryStreamBridge, RunManager, StreamBridge
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from pydantic import ValidationError

from dayboard.agent.budget import ProviderBudgetEstimate, ProviderBudgetExceeded, ProviderBudgetGuard
from dayboard.agent.factory import build_dayboard_agent
from dayboard.agent.observability import project_runtime_event
from dayboard.agent.presentation import project_runtime_stream_event
from agent_platform.application import AgentRunService, CommandSubmissionService, ConversationService
from dayboard.app.clarifications import ClarificationService
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.platform_services import (
    build_platform_services,
)
from dayboard.config import Settings, get_settings
from agent_platform.core import CommandSubmission, TenantContext
from agent_platform.ports import PlatformUnitOfWork
from dayboard.db.provider_usage_repository import ProviderUsageRepository
from dayboard.db.session import SessionLocal, get_session
from agent_platform.core import AgentRunStatus
from agent_platform.core import ConversationRole
from dayboard.domain.interactions import (
    CalendarEntryChoiceCandidate,
    CalendarEntryChoiceOption,
    CalendarEntryChoicePresentation,
    ClarificationPayload,
    SuggestedChoiceCandidate,
    SuggestedChoiceOption,
    SuggestedChoicePresentation,
)

logger = structlog.get_logger(__name__)

USER_VISIBLE_RUNTIME_EVENTS = frozenset(
    {
        "tool_call_started",
        "tool_call_completed",
        "tool_call_error",
    }
)


@dataclass(frozen=True, slots=True)
class ClarificationRunSubmission:
    creation: CommandSubmission
    request: CommandRequest | None


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
        checkpointer=None,
        conversation_service: ConversationService | None = None,
        run_service: AgentRunService | None = None,
        submission_service: CommandSubmissionService | None = None,
        usage_session_factory=SessionLocal,
        runtime_event_session_factory=SessionLocal,
        stream_bridge: StreamBridge | None = None,
        executor_factory=RunExecutor,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)
        self.checkpointer = checkpointer
        platform = build_platform_services(session)
        self.platform_unit_of_work = platform.unit_of_work
        self.conversations = conversation_service or platform.conversations
        self.runs = run_service or platform.runs
        self.submissions = submission_service or platform.submissions
        self.clarifications = ClarificationService(self.conversations)
        self.usage_session_factory = usage_session_factory
        self.runtime_event_session_factory = runtime_event_session_factory
        self.stream_bridge = stream_bridge or MemoryStreamBridge()
        self.executor_factory = executor_factory

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
    ) -> CommandSubmission:
        creation = await self.submissions.submit(
            context,
            input_message=request.message,
            thread_id=thread_id,
            thread_title=request.message[:80],
            conversation_message=conversation_message,
            idempotency_key=idempotency_key,
            request_identity=(
                f"{thread_id or 'new'}:{request.model_dump_json()}"
                if idempotency_key is not None
                else None
            ),
        )
        logger.info(
            "dayboard.command.run_queued",
            run_id=str(creation.run_id),
            thread_id=str(creation.thread_id),
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
            created=creation.created,
        )
        return creation

    async def create_or_get_clarification_run(
        self,
        context: TenantContext,
        *,
        thread_id: UUID,
        state_version: int,
        option_key: str,
        idempotency_key: str | None = None,
    ) -> ClarificationRunSubmission:
        request_identity = f"{thread_id}:clarification:{state_version}:{option_key}"
        if idempotency_key is not None:
            existing = await self.submissions.find_existing(
                context,
                idempotency_key=idempotency_key,
                request_identity=request_identity,
            )
            if existing is not None:
                return ClarificationRunSubmission(creation=existing, request=None)

        choice = await self.clarifications.resolve_choice(
            context,
            thread_id=thread_id,
            state_version=state_version,
            option_key=option_key,
        )
        request = CommandRequest(message=choice.agent_message)
        creation = await self.submissions.submit(
            context,
            input_message=request.message,
            thread_id=thread_id,
            conversation_message=choice.display_message,
            idempotency_key=idempotency_key,
            request_identity=request_identity if idempotency_key is not None else None,
            consume_interaction_version=state_version,
        )
        logger.info(
            "dayboard.clarification.run_queued",
            run_id=str(creation.run_id),
            thread_id=str(creation.thread_id),
            source_state_version=state_version,
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
            created=creation.created,
        )
        return ClarificationRunSubmission(creation=creation, request=request)

    async def execute_command_run(
        self,
        context: TenantContext,
        request: CommandRequest,
        run_id: UUID,
    ) -> None:
        runs = self.runs
        run = await runs.get_run(context, run_id)
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
        runtime_event_lock = asyncio.Lock()
        presentation_parts: list[dict[str, Any]] = []
        budget_estimate = None
        failure_hook_called = False
        try:
            if status == AgentRunStatus.queued:
                if not await runs.mark_running(context, run):
                    return
                await self.platform_unit_of_work.commit()
            logger.info(
                "dayboard.command.run_started",
                run_id=str(run.id),
                thread_id=str(run.thread_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                message_length=len(request.message),
            )

            estimate = self.budget_guard.estimate(input_text=request.message)
            budget_estimate = estimate
            logger.info(
                "dayboard.command.budget_check_started",
                run_id=str(run.id),
                thread_id=str(run.thread_id),
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
                thread_id=str(run.thread_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
            )
            async def record_progress(
                event_type: str,
                content: str,
                event_metadata: dict[str, Any],
            ) -> None:
                latest = await runs.get_run(context, run.id)
                if latest is not None and AgentRunStatus(latest.status) == AgentRunStatus.cancelled:
                    raise asyncio.CancelledError()
                await runs.append_progress(
                    context,
                    run.id,
                    event_type=event_type,
                    content=content,
                    event_metadata=event_metadata,
                )
                await self.platform_unit_of_work.commit()
                await self._publish_run_event(
                    run.id,
                    event_type,
                    {"content": content, "event_metadata": event_metadata},
                )

            async def record_runtime_event(event) -> None:
                await usage_accumulator(event)
                projected = project_runtime_event(event)
                if projected is None:
                    return
                async with runtime_event_lock:
                    async with self.runtime_event_session_factory() as event_session:
                        event_platform = build_platform_services(event_session)
                        event_unit_of_work = event_platform.unit_of_work
                        event_runs = event_platform.runs
                        latest = await event_runs.get_run(context, run.id)
                        if (
                            latest is not None
                            and AgentRunStatus(latest.status) == AgentRunStatus.cancelled
                        ):
                            raise asyncio.CancelledError()
                        await event_runs.append_progress(
                            context,
                            run.id,
                            event_type=projected.event_type,
                            content=projected.content,
                            event_metadata=projected.metadata,
                            category=projected.category,
                        )
                        await event_unit_of_work.commit()
                if projected.event_type in USER_VISIBLE_RUNTIME_EVENTS:
                    await self._publish_run_event(
                        run.id,
                        projected.event_type,
                        {
                            "content": projected.content,
                            "event_metadata": projected.metadata,
                        },
                    )

            async def record_stream_event(event: RuntimeStreamEvent) -> None:
                projected = project_runtime_stream_event(event)
                if projected is None:
                    return
                if projected.event_type in {"schedule_item_result", "schedule_items_result"}:
                    latest = await runs.get_run_for_update(context, run.id)
                    if latest is None or AgentRunStatus(latest.status) != AgentRunStatus.running:
                        await self.platform_unit_of_work.commit()
                        raise asyncio.CancelledError()
                    projected_parts = (
                        projected.data.get("parts", [])
                        if projected.event_type == "schedule_items_result"
                        else [projected.data]
                    )
                    if not _upsert_presentation_parts(
                        presentation_parts,
                        projected_parts,
                    ):
                        return
                    await self.conversations.upsert_assistant_message(
                        context,
                        thread_id=run.thread_id,
                        run_id=run.id,
                        content="",
                        message_metadata={
                            "status": "running",
                            "parts": presentation_parts,
                        },
                    )
                    await self.platform_unit_of_work.commit()
                # Live presentation is projected from the canonical bridge event by the API.

            async def record_compaction(event: CompactionEvent) -> None:
                await self.conversations.update_summary(
                    context,
                    run.thread_id,
                    event.summary_text,
                )
                await self.platform_unit_of_work.commit()
                logger.info(
                    "dayboard.command.context_compacted",
                    run_id=str(run.id),
                    thread_id=str(run.thread_id),
                    summarized_message_count=len(event.summarized_messages),
                    preserved_message_count=len(event.preserved_messages),
                )

            async def complete_run(result: Any) -> None:
                latest = await runs.get_run(context, run.id)
                if latest is not None and AgentRunStatus(latest.status) == AgentRunStatus.cancelled:
                    raise asyncio.CancelledError()

                clarification_question = _extract_clarification_question(result)
                if clarification_question:
                    clarification_payload = _extract_clarification_payload(result)
                    pending = await self.clarifications.set_pending(
                        context,
                        thread_id=run.thread_id,
                        run_id=run.id,
                        question=clarification_question,
                        payload=clarification_payload,
                    )
                    if not await runs.mark_needs_clarification(
                        context,
                        run,
                        question=clarification_question,
                        event_metadata={
                            "state_version": pending.version,
                            "presentation": clarification_payload.presentation.model_dump(
                                mode="json", exclude_none=True
                            )
                            if clarification_payload.presentation is not None
                            else None,
                        },
                    ):
                        await self.platform_unit_of_work.rollback()
                        raise asyncio.CancelledError()
                    await self.conversations.upsert_assistant_message(
                        context,
                        thread_id=run.thread_id,
                        run_id=run.id,
                        content=clarification_question,
                        message_metadata={
                            "status": "needs_clarification",
                            "parts": presentation_parts,
                        },
                    )
                    await self.platform_unit_of_work.commit()
                    await self._publish_run_event(
                        run.id,
                        "clarification_requested",
                        {"content": clarification_question, "parts": presentation_parts},
                    )
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
                    await self.platform_unit_of_work.rollback()
                    raise asyncio.CancelledError()
                await self.conversations.upsert_assistant_message(
                    context,
                    thread_id=run.thread_id,
                    run_id=run.id,
                    content=message,
                    message_metadata={"status": "completed", "parts": presentation_parts},
                )
                await self.conversations.clear_interaction(context, run.thread_id)
                await self.platform_unit_of_work.commit()
                await self._publish_run_event(
                    run.id,
                    "run_completed",
                    {"content": message, "parts": presentation_parts},
                )
                logger.info(
                    "dayboard.command.completed",
                    run_id=str(run.id),
                    tenant_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                    result_length=len(message),
                )

            async def fail_run(exc: Exception) -> None:
                nonlocal failure_hook_called
                failure_hook_called = True
                transitioned = await _mark_run_failed(
                    runs,
                    self.conversations,
                    self.platform_unit_of_work,
                    context,
                    run_id,
                    exc,
                    presentation_parts=presentation_parts,
                )
                if transitioned:
                    await self._publish_run_event(
                        run_id,
                        "run_failed",
                        {
                            "content": _safe_error_message(exc),
                            "parts": presentation_parts,
                        },
                    )

            north_runs = RunManager()
            north_record = north_runs.create(
                thread_id=str(run.thread_id),
                run_id=str(run.id),
            )
            executor = self.executor_factory(self.stream_bridge, north_runs)
            await executor.execute(
                north_record,
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
                        "checkpoint_ns": "dayboard-time-v2",
                    }
                },
                context={
                    "tenant_id": str(context.tenant_id),
                    "user_id": str(context.user_id),
                    "run_id": str(run.id),
                },
                event_sink=record_runtime_event,
                stream_observer=record_stream_event,
                lifecycle_hooks=RunLifecycleHooks(
                    on_completed=complete_run,
                    on_error=fail_run,
                ),
            )
        except Exception as exc:
            transitioned_to_failed = False
            if not failure_hook_called:
                transitioned_to_failed = await _mark_run_failed(
                    runs,
                    self.conversations,
                    self.platform_unit_of_work,
                    context,
                    run_id,
                    exc,
                    presentation_parts=presentation_parts,
                )
            if transitioned_to_failed:
                await self._publish_run_event(
                    run_id,
                    "run_failed",
                    {
                        "content": _safe_error_message(exc),
                        "parts": presentation_parts,
                    },
                )
            logger.exception(
                "dayboard.command.failed",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            await self._settle_provider_usage(
                context, run_id, usage_accumulator, budget_estimate
            )

    async def _settle_provider_usage(
        self,
        context: TenantContext,
        run_id: UUID,
        usage_accumulator: RuntimeUsageAccumulator,
        budget_estimate: ProviderBudgetEstimate | None,
    ) -> None:
        usage = usage_accumulator.total
        if usage is None:
            return
        provider, _, _ = self.settings.agent_model_name.partition(":")
        try:
            async with self.usage_session_factory() as usage_session:
                settlement = await ProviderUsageRepository(usage_session).settle(
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
            reconciled_tokens = 0
            if settlement.created and budget_estimate is not None:
                try:
                    reconciled_tokens = self.budget_guard.reconcile_actual(
                        context=context,
                        model_name=self.settings.agent_model_name,
                        estimate=budget_estimate,
                        actual_tokens=usage.total_tokens,
                    )
                except Exception:
                    logger.exception(
                        "dayboard.command.provider_budget_reconciliation_failed",
                        run_id=str(run_id),
                        tenant_id=str(context.tenant_id),
                        user_id=str(context.user_id),
                        model=self.settings.agent_model_name,
                    )
            logger.info(
                "dayboard.command.provider_usage_settled",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                reconciled_tokens=reconciled_tokens,
                usage_record_created=settlement.created,
            )
        except Exception:
            logger.exception(
                "dayboard.command.provider_usage_settlement_failed",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.settings.agent_model_name,
            )

    async def _publish_run_event(
        self,
        run_id: UUID,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        try:
            await self.stream_bridge.publish(str(run_id), event_type, data)
        except Exception:
            logger.warning(
                "dayboard.command.run_stream_publish_failed",
                run_id=str(run_id),
                event_type=event_type,
                exc_info=True,
            )

    async def fail_command_run(
        self,
        context: TenantContext,
        run_id: UUID,
        exc: Exception,
    ) -> None:
        runs = self.runs
        run = await runs.get_run(context, run_id)
        if run is None:
            raise LookupError(f"Run {run_id} not found")
        transitioned = await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        if not transitioned:
            await self.platform_unit_of_work.rollback()
            return
        await self.conversations.append_message(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            role=ConversationRole.assistant,
            content=_safe_error_message(exc),
            message_metadata={"status": "failed"},
        )
        await self.platform_unit_of_work.commit()


async def _mark_run_failed(
    runs: AgentRunService,
    conversations: ConversationService,
    unit_of_work: PlatformUnitOfWork,
    context: TenantContext,
    run_id: UUID,
    exc: Exception,
    *,
    presentation_parts: list[dict[str, Any]] | None = None,
) -> bool:
    try:
        await unit_of_work.rollback()
        run = await runs.get_run(context, run_id)
        if run is None:
            return False
        transitioned = await runs.mark_failed(
            context,
            run,
            error_type=type(exc).__name__,
            error_message=_safe_error_message(exc),
        )
        if not transitioned:
            await unit_of_work.rollback()
            return False
        await conversations.upsert_assistant_message(
            context,
            thread_id=run.thread_id,
            run_id=run.id,
            content=_safe_error_message(exc),
            message_metadata={
                "status": "failed",
                "parts": presentation_parts or [],
            },
        )
        await unit_of_work.commit()
        return True
    except Exception:
        try:
            await unit_of_work.rollback()
        except Exception:
            logger.exception(
                "dayboard.command.failed_status_rollback_failed",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
            )
        logger.exception(
            "dayboard.command.failed_status_update_failed",
            run_id=str(run_id),
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
        )
        return False


def _presentation_entity_key(part: dict[str, Any]) -> tuple[str, str] | None:
    item = part.get("item")
    if not isinstance(item, dict):
        return None
    value = item.get("value")
    kind = item.get("kind")
    item_id = value.get("id") if isinstance(value, dict) else None
    if not isinstance(kind, str) or not isinstance(item_id, str):
        return None
    return kind, item_id


def _upsert_presentation_parts(
    current: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> bool:
    changed = False
    for part in candidates:
        key = _presentation_entity_key(part)
        if key is None:
            continue
        index = next(
            (
                index
                for index, existing in enumerate(current)
                if _presentation_entity_key(existing) == key
            ),
            None,
        )
        if index is None:
            current.append(part)
            changed = True
        elif current[index] != part:
            current[index] = part
            changed = True
    return changed


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, ProviderBudgetExceeded):
        if exc.budget_type == "request":
            return "请求有点频繁，请稍等一分钟后再试。"
        return "今天的 AI 使用额度已用完，请明天再试。"
    if getattr(exc, "status_code", None) == 429:
        return "AI 服务当前有点繁忙，请稍等几分钟后再试。"
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


def _extract_clarification_payload(result: Any) -> ClarificationPayload:
    fallback = ClarificationPayload(response_kind="free_text")
    if not isinstance(result, dict):
        return fallback

    payload = fallback
    thread_data = result.get("thread_data")
    clarification = thread_data.get("clarification") if isinstance(thread_data, dict) else None
    if isinstance(clarification, dict) and clarification.get("response_kind") == "single_choice":
        options = clarification.get("options")
        if isinstance(options, list):
            choices = [
                SuggestedChoiceCandidate(
                    key=f"candidate_{index}",
                    value=option,
                    label=option,
                )
                for index, option in enumerate(
                    (option for option in options[:10] if isinstance(option, str) and option.strip()),
                    start=1,
                )
            ]
            if choices:
                payload = ClarificationPayload(
                    response_kind="single_choice",
                    candidates=choices,
                    presentation=SuggestedChoicePresentation(
                        options=[
                            SuggestedChoiceOption(key=choice.key, label=choice.label)
                            for choice in choices
                        ]
                    ),
                )

    if not isinstance(result.get("messages"), list):
        return payload

    search_calls: dict[str, dict[str, Any]] = {}
    latest: Any | None = None
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
            artifact = message.artifact
        elif isinstance(message, dict) and message.get("type") == "tool":
            call_id = message.get("tool_call_id")
            artifact = message.get("artifact")
        else:
            continue
        if isinstance(call_id, str) and call_id in search_calls:
            latest = artifact

    if latest is None:
        return payload
    artifact = latest
    if not isinstance(artifact, dict) or artifact.get("type") != "schedule_items_result":
        return payload
    artifact_items = artifact.get("items")
    if not isinstance(artifact_items, list):
        return payload
    content = [
        item["value"]
        for item in artifact_items
        if isinstance(item, dict)
        and item.get("kind") == "calendar"
        and isinstance(item.get("value"), dict)
    ]

    candidates: list[CalendarEntryChoiceCandidate] = []
    for index, item in enumerate(content[:10], start=1):
        try:
            candidates.append(
                CalendarEntryChoiceCandidate.model_validate(
                    {"kind": "calendar", "key": f"candidate_{index}", **item}
                )
            )
        except ValidationError:
            continue
    if not candidates:
        return payload
    return ClarificationPayload(
        response_kind="calendar_choice",
        candidates=candidates,
        presentation=CalendarEntryChoicePresentation(
            options=[
                CalendarEntryChoiceOption.model_validate(
                    candidate.model_dump(
                        exclude={"kind", "id", "row_version", "status"}
                    )
                )
                for candidate in candidates
            ]
        ),
    )


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
