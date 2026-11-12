"""SQLAlchemy transaction boundary for Reminder inbox and delivery use cases."""

from sqlalchemy.ext.asyncio import AsyncSession
from dayboard.app.reminder_ports import ReminderDeliveryStore, ReminderSourceStore

from dayboard.db.reminder_repositories import ReminderDeliveryRepository, ReminderSourceRepository


class SqlAlchemyReminderUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.deliveries: ReminderDeliveryStore = ReminderDeliveryRepository(session)
        self.sources: ReminderSourceStore = ReminderSourceRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
