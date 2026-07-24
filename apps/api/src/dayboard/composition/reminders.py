"""Composition root for Dayboard Reminder services."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.reminders import ReminderService
from dayboard.db.reminder_uow import SqlAlchemyReminderUnitOfWork


@dataclass(frozen=True, slots=True)
class ReminderServiceScope:
    unit_of_work: SqlAlchemyReminderUnitOfWork
    reminders: ReminderService


def build_reminder_services(session: AsyncSession) -> ReminderServiceScope:
    unit_of_work = SqlAlchemyReminderUnitOfWork(session)
    return ReminderServiceScope(
        unit_of_work=unit_of_work,
        reminders=ReminderService(unit_of_work),
    )
