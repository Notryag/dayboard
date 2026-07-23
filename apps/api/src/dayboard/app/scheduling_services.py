"""Composition root for Dayboard scheduling services."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.schedule_queries import ScheduleQueryService
from dayboard.app.scheduling import SchedulingService
from dayboard.db.scheduling_uow import SqlAlchemySchedulingUnitOfWork


@dataclass(frozen=True, slots=True)
class SchedulingServiceScope:
    unit_of_work: SqlAlchemySchedulingUnitOfWork
    scheduling: SchedulingService
    queries: ScheduleQueryService


def build_scheduling_services(session: AsyncSession) -> SchedulingServiceScope:
    unit_of_work = SqlAlchemySchedulingUnitOfWork(session)
    return SchedulingServiceScope(
        unit_of_work=unit_of_work,
        scheduling=SchedulingService(unit_of_work),
        queries=ScheduleQueryService(unit_of_work),
    )


def build_scheduling_service(session: AsyncSession) -> SchedulingService:
    return build_scheduling_services(session).scheduling


def build_schedule_query_service(session: AsyncSession) -> ScheduleQueryService:
    return build_scheduling_services(session).queries
