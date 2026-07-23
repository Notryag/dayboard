"""SQLAlchemy Unit of Work for reusable application-platform stores."""

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.db.conversation_repositories import (
    ConversationMessageRepository,
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
        self.threads = ConversationThreadRepository(session)
        self.messages = ConversationMessageRepository(session)
        self.states = ConversationStateRepository(session)
        self.runs = AgentRunRepository(session)
        self.events = AgentRunEventRepository(session)
        self.idempotency = PostgresIdempotencyStore(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
