from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from north import RunExecutor
from north.runtime import MemoryStreamBridge, StreamBridge
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from agent_platform.core import CommandSubmission, TenantContext
from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.app.clarifications import ClarificationService
from dayboard.app.command_schemas import CommandRequest
from dayboard.app.platform_services import build_platform_services
from dayboard.app.provider_usage import ProviderUsageService
from dayboard.app.run_execution import DayboardRunExecutionDriver
from dayboard.app.run_result_projection import project_run_failure
from dayboard.config import Settings, get_settings
from dayboard.db.session import SessionLocal, get_session


logger = structlog.get_logger(__name__)


def get_command_service(session: AsyncSession = Depends(get_session)) -> CommandService:
    return CommandService(session)


class CommandService:
    """Submit Dayboard commands and delegate persisted Run execution to Platform."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
        budget_guard: ProviderBudgetGuard | None = None,
        provider_usage: ProviderUsageService | None = None,
        checkpointer=None,
        runtime_event_session_factory=SessionLocal,
        stream_bridge: StreamBridge | None = None,
        executor_factory=RunExecutor,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)
        self.provider_usage = provider_usage
        self.checkpointer = checkpointer
        self.platform = build_platform_services(session)
        self.clarifications = ClarificationService(self.platform.conversations)
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
        creation = await self.platform.submissions.submit(
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
            existing = await self.platform.submissions.find_existing(
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
        creation = await self.platform.submissions.submit(
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

    async def execute_command_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> None:
        if self.provider_usage is None:
            raise RuntimeError("Provider usage service is required for Run execution")
        driver = DayboardRunExecutionDriver(
            self.session,
            settings=self.settings,
            unit_of_work=self.platform.unit_of_work,
            conversations=self.platform.conversations,
            runs=self.platform.runs,
            budget_guard=self.budget_guard,
            provider_usage=self.provider_usage,
            checkpointer=self.checkpointer,
            runtime_event_session_factory=self.runtime_event_session_factory,
            stream_bridge=self.stream_bridge,
            executor_factory=self.executor_factory,
        )
        await self.platform.execution.execute(context, run_id, driver)

    async def fail_command_run(
        self,
        context: TenantContext,
        run_id: UUID,
        exc: Exception,
    ) -> None:
        await self.platform.execution.fail(
            context,
            run_id,
            project_run_failure(exc, presentation_parts=[]),
        )
