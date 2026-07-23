"""Composition root for reusable application-platform services."""

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.conversation_service import ConversationService
from agent_platform.run_service import AgentRunService

from dayboard.db.conversation_repositories import (
    ConversationMessageRepository,
    ConversationStateRepository,
    ConversationThreadRepository,
)
from dayboard.db.run_repositories import AgentRunEventRepository, AgentRunRepository


def build_conversation_service(session: AsyncSession) -> ConversationService:
    return ConversationService(
        threads=ConversationThreadRepository(session),
        messages=ConversationMessageRepository(session),
        states=ConversationStateRepository(session),
    )


def build_run_service(session: AsyncSession) -> AgentRunService:
    return AgentRunService(
        runs=AgentRunRepository(session),
        events=AgentRunEventRepository(session),
    )
