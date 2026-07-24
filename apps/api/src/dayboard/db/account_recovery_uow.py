"""SQLAlchemy transaction boundary for account recovery use cases."""

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.db.account_recovery_repository import AccountRecoveryRepository


class SqlAlchemyAccountRecoveryUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.recovery = AccountRecoveryRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
