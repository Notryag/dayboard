"""SQLAlchemy transaction boundary for Dayboard scheduling use cases."""

from sqlalchemy.ext.asyncio import AsyncSession
from dayboard.app.scheduling_ports import CalendarEntryStore, TaskItemStore, ReminderScheduleStore

from dayboard.db.reminder_repositories import ReminderDeliveryRepository
from dayboard.db.repositories import CalendarEntryRepository, TaskItemRepository


class SqlAlchemySchedulingUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.calendar_entries: CalendarEntryStore = CalendarEntryRepository(session)
        self.task_items: TaskItemStore = TaskItemRepository(session)
        self.reminders: ReminderScheduleStore = ReminderDeliveryRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
