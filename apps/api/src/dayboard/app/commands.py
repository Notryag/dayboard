from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import structlog

from agent_platform.application import CommandSubmissionService, RunExecutionCoordinator
from agent_platform.core import CommandSubmission, RunExecutionFailure, TenantContext
from dayboard.app.clarifications import ClarificationService
from dayboard.app.command_schemas import CommandRequest


logger = structlog.get_logger(__name__)


class CommandService:
    """Submit or fail persisted Dayboard commands through Platform use cases."""

    def __init__(
        self,
        submissions: CommandSubmissionService,
        clarifications: ClarificationService,
        execution: RunExecutionCoordinator,
        failure_projector: Callable[[Exception], RunExecutionFailure],
    ) -> None:
        self.submissions = submissions
        self.clarifications = clarifications
        self.execution = execution
        self.failure_projector = failure_projector

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
    ) -> CommandSubmission:
        request_identity = f"{thread_id}:clarification:{state_version}:{option_key}"
        if idempotency_key is not None:
            existing = await self.submissions.find_existing(
                context,
                idempotency_key=idempotency_key,
                request_identity=request_identity,
            )
            if existing is not None:
                return existing

        choice = await self.clarifications.resolve_choice(
            context,
            thread_id=thread_id,
            state_version=state_version,
            option_key=option_key,
        )
        creation = await self.submissions.submit(
            context,
            input_message=choice.agent_message,
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
        return creation

    async def fail_command_run(
        self,
        context: TenantContext,
        run_id: UUID,
        exc: Exception,
    ) -> None:
        await self.execution.fail(
            context,
            run_id,
            self.failure_projector(exc),
        )
