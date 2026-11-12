"""SQLAlchemy Unit of Work for reusable application-platform stores."""

from sqlalchemy.ext.asyncio import AsyncSession
from agent_platform.ports.conversations import ConversationStateStore, ConversationThreadStore
from agent_platform.ports.idempotency import IdempotencyStore
from agent_platform.ports.runs import RunEventStore, RunStore

from dayboard.db.conversation_repositories import (
    ConversationStateRepository,
    ConversationThreadRepository,
)
from dayboard.db.run_repositories import (
    AgentRunEventRepository,
    AgentRunRepository,
    PostgresIdempotencyStore,
)


class SqlAlchemyPlatformUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.threads: ConversationThreadStore = ConversationThreadRepository(session)
        self.states: ConversationStateStore = ConversationStateRepository(session)
        self.runs: RunStore = AgentRunRepository(session)
        self.events: RunEventStore = AgentRunEventRepository(session)
        self.idempotency: IdempotencyStore = PostgresIdempotencyStore(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
