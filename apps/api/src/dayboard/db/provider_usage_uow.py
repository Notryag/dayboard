"""SQLAlchemy transaction boundary for provider usage settlement."""

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.db.provider_usage_repository import ProviderUsageRepository


class SqlAlchemyProviderUsageUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.usage = ProviderUsageRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
