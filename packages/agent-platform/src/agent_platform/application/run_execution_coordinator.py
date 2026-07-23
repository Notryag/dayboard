"""Transactional Run lifecycle coordination around an injected execution driver."""

from __future__ import annotations

import asyncio
from uuid import UUID

from agent_platform.application.conversation_service import ConversationService
from agent_platform.application.run_service import AgentRunService
from agent_platform.core.events import build_interaction_state_event_extension
from agent_platform.core.execution import (
    RunExecutionFailure,
    RunExecutionOutcome,
    RunExecutionOutcomeKind,
)
from agent_platform.core.identity import TenantContext
from agent_platform.core.runs import AgentRunStatus
from agent_platform.ports.execution import RunExecutionDriver
from agent_platform.ports.unit_of_work import PlatformUnitOfWork


TERMINAL_RUN_STATUSES = frozenset(
    {
        AgentRunStatus.completed,
        AgentRunStatus.failed,
        AgentRunStatus.cancelled,
        AgentRunStatus.needs_clarification,
    }
)


class RunExecutionCoordinator:
    def __init__(self, unit_of_work: PlatformUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.runs = AgentRunService(unit_of_work)
        self.conversations = ConversationService(unit_of_work)

    async def execute(
        self,
        context: TenantContext,
        run_id: UUID,
        driver: RunExecutionDriver,
    ) -> None:
        try:
            run = await self.runs.get_run(context, run_id)
            if run is None:
                raise LookupError(f"Run {run_id} not found")
            if run.status in TERMINAL_RUN_STATUSES:
                await self.unit_of_work.rollback()
                return
            if run.status == AgentRunStatus.queued:
                if not await self.runs.mark_running(context, run):
                    await self.unit_of_work.rollback()
                    return
                await self.unit_of_work.commit()
                run = run.model_copy(update={"status": AgentRunStatus.running})
            else:
                await self.unit_of_work.rollback()
        except BaseException:
            await self.unit_of_work.rollback()
            raise

        settled = False

        async def complete(outcome: RunExecutionOutcome) -> None:
            nonlocal settled
            if settled:
                raise RuntimeError("Run execution was already settled")
            await self._complete(context, run_id, outcome)
            settled = True

        async def fail(failure: RunExecutionFailure) -> bool:
            nonlocal settled
            if settled:
                return False
            transitioned = await self.fail(context, run_id, failure)
            settled = True
            return transitioned

        try:
            await driver.execute(
                context,
                run,
                on_completed=complete,
                on_failed=fail,
            )
            if not settled:
                raise RuntimeError("Run execution driver returned without settling the Run")
        except asyncio.CancelledError:
            await self.unit_of_work.rollback()
            raise
        except Exception as exc:
            if not settled:
                await self.fail(context, run_id, driver.failure_from_exception(exc))
            raise

    async def fail(
        self,
        context: TenantContext,
        run_id: UUID,
        failure: RunExecutionFailure,
    ) -> bool:
        try:
            await self.unit_of_work.rollback()
            run = await self.runs.get_run_for_update(context, run_id)
            if run is None:
                raise LookupError(f"Run {run_id} not found")
            if run.status in TERMINAL_RUN_STATUSES:
                await self.unit_of_work.rollback()
                return False
            transitioned = await self.runs.mark_failed(
                context,
                run,
                error_type=failure.error_type,
                error_message=failure.error_message,
            )
            if not transitioned:
                await self.unit_of_work.rollback()
                return False
            await self.conversations.upsert_assistant_message(
                context,
                thread_id=run.thread_id,
                run_id=run.id,
                content=failure.error_message,
                presentation=failure.presentation,
            )
            await self.unit_of_work.commit()
            return True
        except BaseException:
            await self.unit_of_work.rollback()
            raise

    async def _complete(
        self,
        context: TenantContext,
        run_id: UUID,
        outcome: RunExecutionOutcome,
    ) -> None:
        try:
            run = await self.runs.get_run_for_update(context, run_id)
            if run is None or run.status != AgentRunStatus.running:
                await self.unit_of_work.rollback()
                raise asyncio.CancelledError()

            if outcome.kind == RunExecutionOutcomeKind.needs_interaction:
                assert outcome.interaction is not None
                assert outcome.interaction_expires_at is not None
                if outcome.interaction.source_run_id != run.id:
                    raise ValueError("Interaction source_run_id must match the completing Run")
                state = await self.conversations.set_interaction(
                    context,
                    thread_id=run.thread_id,
                    interaction=outcome.interaction,
                    expires_at=outcome.interaction_expires_at,
                )
                transitioned = await self.runs.mark_needs_clarification(
                    context,
                    run,
                    question=outcome.result_message,
                    extension=build_interaction_state_event_extension(state.version),
                )
            else:
                transitioned = await self.runs.mark_completed(
                    context,
                    run,
                    result_message=outcome.result_message,
                )
                await self.conversations.clear_interaction(context, run.thread_id)

            if not transitioned:
                await self.unit_of_work.rollback()
                raise asyncio.CancelledError()
            await self.conversations.upsert_assistant_message(
                context,
                thread_id=run.thread_id,
                run_id=run.id,
                content=outcome.result_message,
                presentation=outcome.presentation,
            )
            await self.unit_of_work.commit()
        except BaseException:
            await self.unit_of_work.rollback()
            raise
