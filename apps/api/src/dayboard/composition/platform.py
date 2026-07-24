"""Composition root for reusable application-platform services."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.application import (
    AgentRunService,
    CommandSubmissionService,
    ConversationService,
    IdempotencyService,
    RunExecutionCoordinator,
)
from agent_platform.ports import PlatformUnitOfWork, PlatformUnitOfWorkFactory

from dayboard.db.platform_uow import SqlAlchemyPlatformUnitOfWork
from dayboard.db.session import SessionLocal


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True, slots=True)
class PlatformServiceScope:
    unit_of_work: SqlAlchemyPlatformUnitOfWork
    conversations: ConversationService
    runs: AgentRunService
    submissions: CommandSubmissionService
    idempotency: IdempotencyService
    execution: RunExecutionCoordinator


def build_platform_unit_of_work(session: AsyncSession) -> SqlAlchemyPlatformUnitOfWork:
    return SqlAlchemyPlatformUnitOfWork(session)


def build_platform_unit_of_work_factory(
    session_factory: SessionFactory = SessionLocal,
) -> PlatformUnitOfWorkFactory:
    @asynccontextmanager
    async def create_unit_of_work() -> AsyncIterator[PlatformUnitOfWork]:
        async with session_factory() as session:
            yield build_platform_unit_of_work(session)

    return create_unit_of_work


def build_platform_services(session: AsyncSession) -> PlatformServiceScope:
    unit_of_work = build_platform_unit_of_work(session)
    return PlatformServiceScope(
        unit_of_work=unit_of_work,
        conversations=ConversationService(unit_of_work),
        runs=AgentRunService(unit_of_work),
        submissions=CommandSubmissionService(unit_of_work),
        idempotency=IdempotencyService(unit_of_work),
        execution=RunExecutionCoordinator(unit_of_work),
    )


def build_conversation_service(session: AsyncSession) -> ConversationService:
    return ConversationService(build_platform_unit_of_work(session))


def build_run_service(session: AsyncSession) -> AgentRunService:
    return AgentRunService(build_platform_unit_of_work(session))


def build_command_submission_service(session: AsyncSession) -> CommandSubmissionService:
    return CommandSubmissionService(build_platform_unit_of_work(session))


def build_idempotency_service(session: AsyncSession) -> IdempotencyService:
    return IdempotencyService(build_platform_unit_of_work(session))
