"""Atomic command submission shared by conversational products."""

from __future__ import annotations

from uuid import UUID, uuid4

from agent_platform.application.conversation_service import ConversationService
from agent_platform.application.idempotency_service import IdempotencyService
from agent_platform.application.run_service import AgentRunService
from agent_platform.core.commands import CommandSubmission
from agent_platform.core.conversations import ConversationRole
from agent_platform.core.errors import IdempotencyTargetNotFoundError
from agent_platform.core.identity import TenantContext
from agent_platform.ports.unit_of_work import PlatformUnitOfWork


class CommandSubmissionService:
    """Create an idempotent Run and its durable conversation input atomically."""

    def __init__(self, unit_of_work: PlatformUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.conversations = ConversationService(unit_of_work)
        self.runs = AgentRunService(unit_of_work)
        self.idempotency = IdempotencyService(unit_of_work)

    async def find_existing(
        self,
        context: TenantContext,
        *,
        idempotency_key: str,
        request_identity: str,
    ) -> CommandSubmission | None:
        try:
            record = await self.idempotency.find_matching(
                context,
                key=idempotency_key,
                request_identity=request_identity,
            )
            if record is None:
                await self.unit_of_work.commit()
                return None
            run = await self.runs.get_run(context, record.run_id)
            if run is None:
                raise IdempotencyTargetNotFoundError(
                    "Idempotency key references a missing run"
                )
            await self.unit_of_work.commit()
            return CommandSubmission(
                run_id=run.id,
                status=run.status,
                created=False,
                thread_id=run.thread_id,
            )
        except BaseException:
            await self.unit_of_work.rollback()
            raise

    async def submit(
        self,
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None = None,
        thread_title: str | None = None,
        conversation_message: str | None = None,
        idempotency_key: str | None = None,
        request_identity: str | None = None,
        consume_interaction_version: int | None = None,
    ) -> CommandSubmission:
        try:
            run_id: UUID | None = None
            if idempotency_key is not None:
                if request_identity is None:
                    raise ValueError("request_identity is required with an idempotency key")
                claim = await self.idempotency.claim(
                    context,
                    key=idempotency_key,
                    request_identity=request_identity,
                    run_id=uuid4(),
                )
                if not claim.created:
                    existing = await self.runs.get_run(context, claim.record.run_id)
                    if existing is None:
                        raise IdempotencyTargetNotFoundError(
                            "Idempotency key references a missing run"
                        )
                    await self.unit_of_work.commit()
                    return CommandSubmission(
                        run_id=existing.id,
                        status=existing.status,
                        created=False,
                        thread_id=existing.thread_id,
                    )
                run_id = claim.record.run_id

            if thread_id is None:
                thread = await self.conversations.create_thread(
                    context,
                    title=thread_title,
                )
                thread_id = thread.id
            else:
                await self.conversations.require_active_thread(context, thread_id)

            if consume_interaction_version is not None:
                await self.conversations.consume_interaction(
                    context,
                    thread_id=thread_id,
                    expected_version=consume_interaction_version,
                )

            run = await self.runs.create_run(
                context,
                input_message=input_message,
                thread_id=thread_id,
                run_id=run_id,
            )
            await self.conversations.append_message(
                context,
                thread_id=thread_id,
                run_id=run.id,
                role=ConversationRole.user,
                content=(
                    conversation_message if conversation_message is not None else input_message
                ),
            )
            await self.unit_of_work.commit()
            return CommandSubmission(
                run_id=run.id,
                status=run.status,
                created=True,
                thread_id=run.thread_id,
            )
        except BaseException:
            await self.unit_of_work.rollback()
            raise
