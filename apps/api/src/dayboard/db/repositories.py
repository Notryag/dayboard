from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
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

    async def search_active(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        title_query: str | None = None,
    ) -> list[CalendarEntryRow]:
        conditions = [
            CalendarEntryRow.tenant_id == context.tenant_id,
            CalendarEntryRow.owner_user_id == context.user_id,
            CalendarEntryRow.deleted_at.is_(None),
            CalendarEntryRow.start_time >= start_time,
            CalendarEntryRow.start_time < end_time,
        ]
        if title_query:
            conditions.append(CalendarEntryRow.title.ilike(f"%{title_query}%"))
        result = await self.session.scalars(
            select(CalendarEntryRow)
            .where(*conditions)
            .order_by(CalendarEntryRow.start_time.asc())
        )
        return list(result)

    async def get(self, context: TenantContext, entry_id: UUID) -> CalendarEntryRow | None:
        return await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.deleted_at.is_(None),
            )
        )

    async def get_by_updated_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> CalendarEntryRow | None:
        return await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.updated_by_run_id == run_id,
                CalendarEntryRow.deleted_at.is_(None),
            )
        )

    async def reschedule(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        start_time: datetime,
        end_time: datetime,
        expected_updated_at: datetime,
        updated_by_run_id: UUID,
    ) -> CalendarEntryRow | None:
        return await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.updated_at == expected_updated_at,
                CalendarEntryRow.deleted_at.is_(None),
            )
            .values(
                start_time=start_time,
                end_time=end_time,
                updated_by_run_id=updated_by_run_id,
                updated_at=func.now(),
            )
            .returning(CalendarEntryRow)
        )

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> CalendarEntryRow | None:
        return await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.created_by_run_id == run_id,
                CalendarEntryRow.deleted_at.is_(None),
            )
        )

    async def list_overlapping(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        default_duration: timedelta,
        exclude_entry_id: UUID | None = None,
    ) -> list[CalendarEntryRow]:
        effective_end = func.coalesce(
            CalendarEntryRow.end_time,
            CalendarEntryRow.start_time + default_duration,
        )
        conditions = [
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.start_time < end_time,
                effective_end > start_time,
        ]
        if exclude_entry_id is not None:
            conditions.append(CalendarEntryRow.id != exclude_entry_id)
        result = await self.session.scalars(
            select(CalendarEntryRow)
            .where(*conditions)
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

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> TaskItemRow | None:
        return await self.session.scalar(
            select(TaskItemRow).where(
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.created_by_run_id == run_id,
                TaskItemRow.deleted_at.is_(None),
            )
        )
