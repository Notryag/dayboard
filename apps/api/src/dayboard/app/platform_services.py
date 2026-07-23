"""Composition root for reusable application-platform services."""

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.run_service import AgentRunService

from dayboard.db.run_repositories import AgentRunEventRepository, AgentRunRepository


def build_run_service(session: AsyncSession) -> AgentRunService:
    return AgentRunService(
        runs=AgentRunRepository(session),
        events=AgentRunEventRepository(session),
    )
