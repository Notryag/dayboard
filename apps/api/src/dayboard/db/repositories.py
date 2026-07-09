from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.domain.calendar import CalendarEntryCreate
from dayboard.domain.tasks import TaskItemCreate


class CalendarEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, context: TenantContext, data: CalendarEntryCreate) -> CalendarEntryRow:
        row = CalendarEntryRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            title=data.title,
            start_time=data.start_time,
            end_time=data.end_time,
            timezone=data.timezone,
            participants=data.participants,
            reminder=data.reminder.model_dump() if data.reminder else None,
            created_by_run_id=data.created_by_run_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_active(self, context: TenantContext) -> list[CalendarEntryRow]:
        result = await self.session.scalars(
            select(CalendarEntryRow)
            .where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.deleted_at.is_(None),
            )
            .order_by(CalendarEntryRow.start_time.asc())
        )
        return list(result)


class TaskItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, context: TenantContext, data: TaskItemCreate) -> TaskItemRow:
        row = TaskItemRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            title=data.title,
            due_at=data.due_at,
            timezone=data.timezone,
            reminder=data.reminder.model_dump() if data.reminder else None,
            status=data.status.value,
            created_by_run_id=data.created_by_run_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_active(self, context: TenantContext) -> list[TaskItemRow]:
        result = await self.session.scalars(
            select(TaskItemRow)
            .where(
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.deleted_at.is_(None),
            )
            .order_by(TaskItemRow.due_at.asc().nulls_last(), TaskItemRow.created_at.desc())
        )
        return list(result)
