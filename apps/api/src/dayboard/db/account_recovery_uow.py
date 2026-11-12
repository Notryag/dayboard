"""SQLAlchemy transaction boundary for account recovery use cases."""

from sqlalchemy.ext.asyncio import AsyncSession
from dayboard.app.account_recovery_ports import AccountRecoveryStore

from dayboard.db.account_recovery_repository import AccountRecoveryRepository


class SqlAlchemyAccountRecoveryUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.recovery: AccountRecoveryStore = AccountRecoveryRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
