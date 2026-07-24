"""Dayboard adapter from Platform Run execution to the North runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any, Protocol
from uuid import UUID

from langchain_core.messages import HumanMessage
from north import (
    CompactionEvent,
    CompactionHook,
    RunExecutor,
    RunLifecycleHooks,
    RuntimeExecutionResult,
    RuntimeStreamEvent,
    RuntimeUsageAccumulator,
)
from north.runtime import RunManager, StreamBridge
import structlog

from agent_platform.application import AgentRunService, ConversationService
from agent_platform.core import (
    AgentRun,
    AgentRunStatus,
    RunExecutionFailure,
    RunExecutionOutcomeKind,
    TenantContext,
)
from agent_platform.ports import PlatformUnitOfWork, PlatformUnitOfWorkFactory
from agent_platform.ports.execution import RunCompletionCallback, RunFailureCallback
from dayboard.agent.budget import ProviderBudgetEstimate, ProviderBudgetGuard
from dayboard.agent.observability import project_runtime_event
from dayboard.agent.presentation import project_runtime_stream_event
from dayboard.app.conversation_presentations import build_dayboard_presentation
from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageCall,
    ProviderUsageSettlementPort,
)
from dayboard.agent.run_result_projection import (
    merge_presentation_parts,
    project_run_failure,
    project_run_result,
)


logger = structlog.get_logger(__name__)

USER_VISIBLE_RUNTIME_EVENTS = frozenset(
    {
        "tool_call_started",
        "tool_call_completed",
        "tool_call_error",
    }
)


class DayboardAgentFactory(Protocol):
    def __call__(
        self,
        context: TenantContext,
        run_id: UUID,
        compaction_hooks: Sequence[CompactionHook],
    ) -> object: ...


RunExecutorFactory = Callable[[StreamBridge, RunManager], RunExecutor]


class DayboardRunExecutionDriver:
    """Execute one persisted Dayboard Run while Platform owns its lifecycle."""

    def __init__(
        self,
        *,
        unit_of_work: PlatformUnitOfWork,
        conversations: ConversationService,
        runs: AgentRunService,
        budget_guard: ProviderBudgetGuard,
        provider_usage: ProviderUsageSettlementPort,
        runtime_event_uow_factory: PlatformUnitOfWorkFactory,
        agent_factory: DayboardAgentFactory,
        model_name: str,
        stream_bridge: StreamBridge,
        executor_factory: RunExecutorFactory = RunExecutor,
    ) -> None:
        self.unit_of_work = unit_of_work
        self.conversations = conversations
        self.runs = runs
        self.budget_guard = budget_guard
        self.provider_usage = provider_usage
        self.runtime_event_uow_factory = runtime_event_uow_factory
        self.agent_factory = agent_factory
        self.model_name = model_name
        self.stream_bridge = stream_bridge
        self.executor_factory = executor_factory
        self.presentation_parts: list[dict[str, Any]] = []

    async def execute(
        self,
        context: TenantContext,
        run: AgentRun,
        *,
        on_completed: RunCompletionCallback,
        on_failed: RunFailureCallback,
    ) -> None:
        usage_accumulator = RuntimeUsageAccumulator()
        runtime_event_lock = asyncio.Lock()
        budget_estimate: ProviderBudgetEstimate | None = None
        terminal_callback_called = False

        async def record_runtime_event(event) -> None:
            await usage_accumulator(event)
            projected = project_runtime_event(event)
            if projected is None:
                return
            async with runtime_event_lock:
                async with self.runtime_event_uow_factory() as event_unit_of_work:
                    event_runs = AgentRunService(event_unit_of_work)
                    try:
                        latest = await event_runs.get_run(context, run.id)
                        if latest is None or latest.status != AgentRunStatus.running:
                            raise asyncio.CancelledError()
                        await event_runs.append_progress(
                            context,
                            run.id,
                            event_type=projected.event_type,
                            content=projected.content,
                            extension=projected.extension,
                            category=projected.category,
                        )
                        await event_unit_of_work.commit()
                    except BaseException:
                        await event_unit_of_work.rollback()
                        raise
            if projected.event_type in USER_VISIBLE_RUNTIME_EVENTS:
                await self._publish_run_event(
                    run.id,
                    projected.event_type,
                    {"content": projected.content},
                )

        async def record_stream_event(event: RuntimeStreamEvent) -> None:
            projected = project_runtime_stream_event(event)
            if projected is None or projected.event_type not in {
                "schedule_item_result",
                "schedule_items_result",
            }:
                return
            projected_parts = (
                projected.data.get("parts", [])
                if projected.event_type == "schedule_items_result"
                else [projected.data]
            )
            if not merge_presentation_parts(self.presentation_parts, projected_parts):
                return
            latest = await self.runs.get_run_for_update(context, run.id)
            if latest is None or latest.status != AgentRunStatus.running:
                await self.unit_of_work.rollback()
                raise asyncio.CancelledError()
            await self.conversations.upsert_assistant_message(
                context,
                thread_id=run.thread_id,
                run_id=run.id,
                content="",
                presentation=build_dayboard_presentation(self.presentation_parts),
            )
            await self.unit_of_work.commit()

        async def record_compaction(event: CompactionEvent) -> None:
            await self.conversations.update_summary(
                context,
                run.thread_id,
                event.summary_text,
            )
            await self.unit_of_work.commit()
            logger.info(
                "dayboard.command.context_compacted",
                run_id=str(run.id),
                thread_id=str(run.thread_id),
                summarized_message_count=len(event.summarized_messages),
                preserved_message_count=len(event.preserved_messages),
            )

        async def complete_run(result: RuntimeExecutionResult) -> None:
            nonlocal terminal_callback_called
            outcome = project_run_result(
                result,
                run_id=run.id,
                presentation_parts=self.presentation_parts,
            )
            await on_completed(outcome)
            terminal_callback_called = True
            event_type = (
                "clarification_requested"
                if outcome.kind == RunExecutionOutcomeKind.needs_interaction
                else "run_completed"
            )
            await self._publish_run_event(
                run.id,
                event_type,
                {"content": outcome.result_message, "parts": self.presentation_parts},
            )
            logger.info(
                (
                    "dayboard.command.needs_clarification"
                    if outcome.kind == RunExecutionOutcomeKind.needs_interaction
                    else "dayboard.command.completed"
                ),
                run_id=str(run.id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                result_length=len(outcome.result_message),
            )

        async def fail_run(exc: Exception) -> None:
            nonlocal terminal_callback_called
            failure = self.failure_from_exception(exc)
            transitioned = await on_failed(failure)
            terminal_callback_called = True
            if transitioned:
                await self._publish_run_event(
                    run.id,
                    "run_failed",
                    {
                        "content": failure.error_message,
                        "parts": self.presentation_parts,
                    },
                )

        try:
            logger.info(
                "dayboard.command.run_started",
                run_id=str(run.id),
                thread_id=str(run.thread_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.model_name,
                message_length=len(run.input_message),
            )
            budget_estimate = self._check_budget(context, run)
            logger.info(
                "dayboard.command.north_invoke_started",
                run_id=str(run.id),
                thread_id=str(run.thread_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.model_name,
            )
            north_runs = RunManager()
            north_record = north_runs.create(
                thread_id=str(run.thread_id),
                run_id=str(run.id),
            )
            executor = self.executor_factory(self.stream_bridge, north_runs)
            await executor.execute(
                north_record,
                agent_factory=lambda: self.agent_factory(
                    context,
                    run.id,
                    [record_compaction],
                ),
                graph_input={"messages": [HumanMessage(content=run.input_message)]},
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not terminal_callback_called:
                transitioned = await on_failed(self.failure_from_exception(exc))
                terminal_callback_called = True
                if transitioned:
                    failure = self.failure_from_exception(exc)
                    await self._publish_run_event(
                        run.id,
                        "run_failed",
                        {
                            "content": failure.error_message,
                            "parts": self.presentation_parts,
                        },
                    )
            logger.exception(
                "dayboard.command.failed",
                run_id=str(run.id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.model_name,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            await self._settle_provider_usage(
                context,
                run.id,
                usage_accumulator,
                budget_estimate,
            )

    def failure_from_exception(self, exc: Exception) -> RunExecutionFailure:
        return project_run_failure(exc, presentation_parts=self.presentation_parts)

    def _check_budget(
        self,
        context: TenantContext,
        run: AgentRun,
    ) -> ProviderBudgetEstimate:
        estimate = self.budget_guard.estimate(input_text=run.input_message)
        logger.info(
            "dayboard.command.budget_check_started",
            run_id=str(run.id),
            thread_id=str(run.thread_id),
            tenant_id=str(context.tenant_id),
            user_id=str(context.user_id),
            model=self.model_name,
            estimated_tokens=estimate.token_units,
            request_units=estimate.request_units,
        )
        self.budget_guard.check(
            context=context,
            model_name=self.model_name,
            estimate=estimate,
        )
        return estimate

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
        provider, _, _ = self.model_name.partition(":")
        try:
            aggregate = ProviderUsageAggregate(
                run_id=run_id,
                provider=provider or "unknown",
                model=self.model_name,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                calls=tuple(
                    ProviderUsageCall(
                        call_id=call["call_id"],
                        input_tokens=call["input_tokens"],
                        output_tokens=call["output_tokens"],
                        total_tokens=call["total_tokens"],
                    )
                    for call in usage_accumulator.calls
                ),
            )
            settlement = await self.provider_usage.settle(
                context,
                aggregate,
            )
            reconciled_tokens = 0
            if settlement.created and budget_estimate is not None:
                try:
                    reconciled_tokens = self.budget_guard.reconcile_actual(
                        context=context,
                        model_name=self.model_name,
                        estimate=budget_estimate,
                        actual_tokens=usage.total_tokens,
                    )
                except Exception:
                    logger.exception(
                        "dayboard.command.provider_budget_reconciliation_failed",
                        run_id=str(run_id),
                        tenant_id=str(context.tenant_id),
                        user_id=str(context.user_id),
                        model=self.model_name,
                    )
            logger.info(
                "dayboard.command.provider_usage_settled",
                run_id=str(run_id),
                tenant_id=str(context.tenant_id),
                user_id=str(context.user_id),
                model=self.model_name,
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
                model=self.model_name,
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
