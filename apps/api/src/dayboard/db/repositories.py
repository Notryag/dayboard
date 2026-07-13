from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.domain.calendar import CalendarEntryCreate
from dayboard.domain.tasks import TaskItemCreate, TaskItemUpdate, TaskStatus


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
            created_operation_key=data.created_operation_key,
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

    async def list_page(
        self,
        context: TenantContext,
        *,
        start_time: datetime | None,
        end_time: datetime | None,
        cursor_start_time: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[CalendarEntryRow]:
        conditions = [
            CalendarEntryRow.tenant_id == context.tenant_id,
            CalendarEntryRow.owner_user_id == context.user_id,
            CalendarEntryRow.deleted_at.is_(None),
        ]
        if start_time is not None:
            conditions.append(CalendarEntryRow.start_time >= start_time)
        if end_time is not None:
            conditions.append(CalendarEntryRow.start_time < end_time)
        if cursor_start_time is not None and cursor_id is not None:
            conditions.append(
                or_(
                    CalendarEntryRow.start_time > cursor_start_time,
                    and_(
                        CalendarEntryRow.start_time == cursor_start_time,
                        CalendarEntryRow.id > cursor_id,
                    ),
                )
            )
        result = await self.session.scalars(
            select(CalendarEntryRow)
            .where(*conditions)
            .order_by(CalendarEntryRow.start_time.asc(), CalendarEntryRow.id.asc())
            .limit(limit)
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

    async def get_including_cancelled(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntryRow | None:
        return await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
            )
        )

    async def get_by_updated_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntryRow | None:
        return await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.updated_by_run_id == run_id,
                CalendarEntryRow.updated_operation_key == operation_key,
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
        operation_key: str,
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
                updated_operation_key=operation_key,
                updated_at=func.now(),
            )
            .returning(CalendarEntryRow)
        )

    async def get_by_cancelled_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntryRow | None:
        return await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.cancelled_by_run_id == run_id,
                CalendarEntryRow.cancelled_operation_key == operation_key,
                CalendarEntryRow.deleted_at.is_not(None),
            )
        )

    async def cancel(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_updated_at: datetime,
        cancelled_by_run_id: UUID,
        operation_key: str,
        cancellation_reason: str | None,
    ) -> CalendarEntryRow | None:
        now = func.now()
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
                deleted_at=now,
                updated_at=now,
                cancelled_by_run_id=cancelled_by_run_id,
                cancelled_operation_key=operation_key,
                cancellation_reason=cancellation_reason,
            )
            .returning(CalendarEntryRow)
        )

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> CalendarEntryRow | None:
        conditions = [
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.created_by_run_id == run_id,
                CalendarEntryRow.deleted_at.is_(None),
        ]
        if operation_key is not None:
            conditions.append(CalendarEntryRow.created_operation_key == operation_key)
        return await self.session.scalar(
            select(CalendarEntryRow).where(*conditions)
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
            created_operation_key=data.created_operation_key,
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

    async def list_page(
        self,
        context: TenantContext,
        *,
        status: TaskStatus | None,
        due_kind: Literal["all", "dated", "undated"],
        due_from: datetime | None,
        due_to: datetime | None,
        cursor_due_at: datetime | None,
        cursor_created_at: datetime | None,
        cursor_id: UUID | None,
        cursor_has_due_at: bool | None,
        limit: int,
    ) -> list[TaskItemRow]:
        conditions = [
            TaskItemRow.tenant_id == context.tenant_id,
            TaskItemRow.owner_user_id == context.user_id,
            TaskItemRow.deleted_at.is_(None),
        ]
        if status is not None:
            conditions.append(TaskItemRow.status == status.value)
        if due_kind == "dated":
            conditions.append(TaskItemRow.due_at.is_not(None))
        elif due_kind == "undated":
            conditions.append(TaskItemRow.due_at.is_(None))
        if due_from is not None:
            conditions.append(TaskItemRow.due_at >= due_from)
        if due_to is not None:
            conditions.append(TaskItemRow.due_at < due_to)
        if cursor_created_at is not None and cursor_id is not None:
            trailing_order = or_(
                TaskItemRow.created_at < cursor_created_at,
                and_(TaskItemRow.created_at == cursor_created_at, TaskItemRow.id < cursor_id),
            )
            if cursor_has_due_at and cursor_due_at is not None:
                conditions.append(
                    or_(
                        TaskItemRow.due_at > cursor_due_at,
                        and_(TaskItemRow.due_at == cursor_due_at, trailing_order),
                        TaskItemRow.due_at.is_(None),
                    )
                )
            else:
                conditions.extend([TaskItemRow.due_at.is_(None), trailing_order])
        result = await self.session.scalars(
            select(TaskItemRow)
            .where(*conditions)
            .order_by(
                TaskItemRow.due_at.asc().nulls_last(),
                TaskItemRow.created_at.desc(),
                TaskItemRow.id.desc(),
            )
            .limit(limit)
        )
        return list(result)

    async def search(
        self,
        context: TenantContext,
        *,
        title_query: str | None = None,
        status: TaskStatus | None = TaskStatus.open,
    ) -> list[TaskItemRow]:
        conditions = [
            TaskItemRow.tenant_id == context.tenant_id,
            TaskItemRow.owner_user_id == context.user_id,
            TaskItemRow.deleted_at.is_(None),
        ]
        if title_query:
            conditions.append(TaskItemRow.title.ilike(f"%{title_query}%"))
        if status is not None:
            conditions.append(TaskItemRow.status == status.value)
        result = await self.session.scalars(
            select(TaskItemRow)
            .where(*conditions)
            .order_by(TaskItemRow.due_at.asc().nulls_last(), TaskItemRow.created_at.desc())
        )
        return list(result)

    async def get(self, context: TenantContext, task_id: UUID) -> TaskItemRow | None:
        return await self.session.scalar(
            select(TaskItemRow).where(
                TaskItemRow.id == task_id,
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.deleted_at.is_(None),
            )
        )

    async def get_by_updated_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> TaskItemRow | None:
        return await self.session.scalar(
            select(TaskItemRow).where(
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.updated_by_run_id == run_id,
                TaskItemRow.updated_operation_key == operation_key,
                TaskItemRow.deleted_at.is_(None),
            )
        )

    async def update(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        data: TaskItemUpdate,
        expected_updated_at: datetime,
    ) -> TaskItemRow | None:
        values = {
            "updated_by_run_id": data.updated_by_run_id,
            "updated_operation_key": data.updated_operation_key,
            "updated_at": func.now(),
        }
        if data.title is not None:
            values["title"] = data.title
        if data.due_at is not None:
            values["due_at"] = data.due_at
        if data.status is not None:
            values["status"] = data.status.value
        return await self.session.scalar(
            update(TaskItemRow)
            .where(
                TaskItemRow.id == task_id,
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.updated_at == expected_updated_at,
                TaskItemRow.deleted_at.is_(None),
            )
            .values(**values)
            .returning(TaskItemRow)
        )

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> TaskItemRow | None:
        conditions = [
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.created_by_run_id == run_id,
                TaskItemRow.deleted_at.is_(None),
        ]
        if operation_key is not None:
            conditions.append(TaskItemRow.created_operation_key == operation_key)
        return await self.session.scalar(
            select(TaskItemRow).where(*conditions)
        )
