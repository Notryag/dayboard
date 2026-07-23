from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import DateTime, and_, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.db.schedule_mappers import calendar_entry_from_row, task_item_from_row
from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, CalendarTimingKind
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskItemUpdate, TaskStatus


SEARCH_RESULT_LIMIT = 50


class CalendarEntryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, context: TenantContext, data: CalendarEntryCreate) -> CalendarEntry:
        row = CalendarEntryRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            title=data.title,
            timing_kind=data.timing_kind.value,
            scheduled_date=data.scheduled_date,
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
        await self.session.refresh(row)
        return calendar_entry_from_row(row)

    async def list_page(
        self,
        context: TenantContext,
        *,
        start_time: datetime | None,
        end_time: datetime | None,
        start_date: date | None,
        end_date: date | None,
        cursor_start_time: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[CalendarEntry]:
        conditions = [
            CalendarEntryRow.tenant_id == context.tenant_id,
            CalendarEntryRow.owner_user_id == context.user_id,
            CalendarEntryRow.deleted_at.is_(None),
        ]
        timed_conditions = [CalendarEntryRow.timing_kind == "timed"]
        anytime_conditions = [CalendarEntryRow.timing_kind == "anytime"]
        if start_time is not None:
            timed_conditions.append(CalendarEntryRow.start_time >= start_time)
        if end_time is not None:
            timed_conditions.append(CalendarEntryRow.start_time < end_time)
        if start_date is not None:
            anytime_conditions.append(CalendarEntryRow.scheduled_date >= start_date)
        if end_date is not None:
            anytime_conditions.append(CalendarEntryRow.scheduled_date < end_date)
        conditions.append(or_(and_(*timed_conditions), and_(*anytime_conditions)))
        sort_time = func.coalesce(
            CalendarEntryRow.start_time,
            cast(CalendarEntryRow.scheduled_date, DateTime(timezone=True)),
        )
        if cursor_start_time is not None and cursor_id is not None:
            conditions.append(
                or_(
                    sort_time > cursor_start_time,
                    and_(
                        sort_time == cursor_start_time,
                        CalendarEntryRow.id > cursor_id,
                    ),
                )
            )
        result = await self.session.scalars(
            select(CalendarEntryRow)
            .where(*conditions)
            .order_by(sort_time.asc(), CalendarEntryRow.id.asc())
            .limit(limit)
        )
        return [calendar_entry_from_row(row) for row in result]

    async def search_active(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        start_date: date,
        end_date: date,
        title_query: str | None = None,
    ) -> list[CalendarEntry]:
        conditions = [
            CalendarEntryRow.tenant_id == context.tenant_id,
            CalendarEntryRow.owner_user_id == context.user_id,
            CalendarEntryRow.deleted_at.is_(None),
            CalendarEntryRow.completed_at.is_(None),
            or_(
                and_(
                    CalendarEntryRow.timing_kind == "timed",
                    CalendarEntryRow.start_time < end_time,
                    func.coalesce(
                        CalendarEntryRow.end_time,
                        CalendarEntryRow.start_time + timedelta(hours=1),
                    )
                    > start_time,
                ),
                and_(
                    CalendarEntryRow.timing_kind == "anytime",
                    CalendarEntryRow.scheduled_date >= start_date,
                    CalendarEntryRow.scheduled_date < end_date,
                ),
            ),
        ]
        if title_query:
            conditions.append(CalendarEntryRow.title.ilike(f"%{title_query}%"))
        result = await self.session.scalars(
            select(CalendarEntryRow)
            .where(*conditions)
            .order_by(
                func.coalesce(
                    CalendarEntryRow.start_time,
                    cast(CalendarEntryRow.scheduled_date, DateTime(timezone=True)),
                ).asc()
            )
            .limit(SEARCH_RESULT_LIMIT)
        )
        return [calendar_entry_from_row(row) for row in result]

    async def get(self, context: TenantContext, entry_id: UUID) -> CalendarEntry | None:
        row = await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.deleted_at.is_(None),
            )
        )
        return calendar_entry_from_row(row) if row else None

    async def get_for_update(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            select(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return calendar_entry_from_row(row) if row else None

    async def get_including_cancelled(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
            )
        )
        return calendar_entry_from_row(row) if row else None

    async def get_by_updated_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.updated_by_run_id == run_id,
                CalendarEntryRow.updated_operation_key == operation_key,
                CalendarEntryRow.deleted_at.is_(None),
            )
        )
        return calendar_entry_from_row(row) if row else None

    async def reschedule(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        timing_kind: CalendarTimingKind,
        scheduled_date: date | None,
        start_time: datetime | None,
        end_time: datetime | None,
        expected_row_version: int,
        updated_by_run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.row_version == expected_row_version,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.completed_at.is_(None),
            )
            .values(
                timing_kind=timing_kind.value,
                scheduled_date=scheduled_date,
                start_time=start_time,
                end_time=end_time,
                reminder=(
                    None if timing_kind is CalendarTimingKind.anytime else CalendarEntryRow.reminder
                ),
                updated_by_run_id=updated_by_run_id,
                updated_operation_key=operation_key,
                row_version=CalendarEntryRow.row_version + 1,
                updated_at=func.now(),
            )
            .returning(CalendarEntryRow)
        )
        return calendar_entry_from_row(row) if row else None

    async def update_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        title: str,
        timing_kind: CalendarTimingKind,
        scheduled_date: date | None,
        start_time: datetime | None,
        end_time: datetime | None,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.row_version == expected_row_version,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.completed_at.is_(None),
            )
            .values(
                title=title,
                timing_kind=timing_kind.value,
                scheduled_date=scheduled_date,
                start_time=start_time,
                end_time=end_time,
                reminder=(
                    None if timing_kind is CalendarTimingKind.anytime else CalendarEntryRow.reminder
                ),
                updated_by_run_id=None,
                updated_operation_key=None,
                row_version=CalendarEntryRow.row_version + 1,
                updated_at=func.now(),
            )
            .returning(CalendarEntryRow)
        )
        return calendar_entry_from_row(row) if row else None

    async def get_by_cancelled_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            select(CalendarEntryRow).where(
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.cancelled_by_run_id == run_id,
                CalendarEntryRow.cancelled_operation_key == operation_key,
                CalendarEntryRow.deleted_at.is_not(None),
            )
        )
        return calendar_entry_from_row(row) if row else None

    async def cancel(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
        cancelled_by_run_id: UUID,
        operation_key: str,
        cancellation_reason: str | None,
    ) -> CalendarEntry | None:
        now = func.now()
        row = await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.row_version == expected_row_version,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.completed_at.is_(None),
            )
            .values(
                deleted_at=now,
                updated_at=now,
                cancelled_by_run_id=cancelled_by_run_id,
                cancelled_operation_key=operation_key,
                cancellation_reason=cancellation_reason,
                row_version=CalendarEntryRow.row_version + 1,
            )
            .returning(CalendarEntryRow)
        )
        return calendar_entry_from_row(row) if row else None

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> CalendarEntry | None:
        conditions = [
            CalendarEntryRow.tenant_id == context.tenant_id,
            CalendarEntryRow.owner_user_id == context.user_id,
            CalendarEntryRow.created_by_run_id == run_id,
            CalendarEntryRow.deleted_at.is_(None),
        ]
        if operation_key is not None:
            conditions.append(CalendarEntryRow.created_operation_key == operation_key)
        row = await self.session.scalar(select(CalendarEntryRow).where(*conditions))
        return calendar_entry_from_row(row) if row else None

    async def cancel_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        now = func.now()
        row = await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.row_version == expected_row_version,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.completed_at.is_(None),
            )
            .values(
                deleted_at=now,
                updated_at=now,
                cancelled_by_run_id=None,
                cancelled_operation_key=None,
                cancellation_reason=None,
                row_version=CalendarEntryRow.row_version + 1,
            )
            .returning(CalendarEntryRow)
        )
        return calendar_entry_from_row(row) if row else None

    async def complete_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        now = func.now()
        row = await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.row_version == expected_row_version,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.completed_at.is_(None),
            )
            .values(
                completed_at=now,
                row_version=CalendarEntryRow.row_version + 1,
                updated_at=now,
            )
            .returning(CalendarEntryRow)
        )
        return calendar_entry_from_row(row) if row else None

    async def reopen_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None:
        row = await self.session.scalar(
            update(CalendarEntryRow)
            .where(
                CalendarEntryRow.id == entry_id,
                CalendarEntryRow.tenant_id == context.tenant_id,
                CalendarEntryRow.owner_user_id == context.user_id,
                CalendarEntryRow.row_version == expected_row_version,
                CalendarEntryRow.deleted_at.is_(None),
                CalendarEntryRow.completed_at.is_not(None),
            )
            .values(
                completed_at=None,
                row_version=CalendarEntryRow.row_version + 1,
                updated_at=func.now(),
            )
            .returning(CalendarEntryRow)
        )
        return calendar_entry_from_row(row) if row else None

    async def list_overlapping(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        default_duration: timedelta,
        exclude_entry_id: UUID | None = None,
    ) -> list[CalendarEntry]:
        effective_end = func.coalesce(
            CalendarEntryRow.end_time,
            CalendarEntryRow.start_time + default_duration,
        )
        conditions = [
            CalendarEntryRow.tenant_id == context.tenant_id,
            CalendarEntryRow.owner_user_id == context.user_id,
            CalendarEntryRow.deleted_at.is_(None),
            CalendarEntryRow.completed_at.is_(None),
            CalendarEntryRow.timing_kind == "timed",
            CalendarEntryRow.start_time < end_time,
            effective_end > start_time,
        ]
        if exclude_entry_id is not None:
            conditions.append(CalendarEntryRow.id != exclude_entry_id)
        result = await self.session.scalars(
            select(CalendarEntryRow).where(*conditions).order_by(CalendarEntryRow.start_time.asc())
        )
        return [calendar_entry_from_row(row) for row in result]


class TaskItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, context: TenantContext, data: TaskItemCreate) -> TaskItem:
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
        await self.session.refresh(row)
        return task_item_from_row(row)

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
    ) -> list[TaskItem]:
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
        return [task_item_from_row(row) for row in result]

    async def search(
        self,
        context: TenantContext,
        *,
        title_query: str | None = None,
        status: TaskStatus | None = TaskStatus.open,
    ) -> list[TaskItem]:
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
            .limit(SEARCH_RESULT_LIMIT)
        )
        return [task_item_from_row(row) for row in result]

    async def get(self, context: TenantContext, task_id: UUID) -> TaskItem | None:
        row = await self.session.scalar(
            select(TaskItemRow).where(
                TaskItemRow.id == task_id,
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.deleted_at.is_(None),
            )
        )
        return task_item_from_row(row) if row else None

    async def get_by_updated_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> TaskItem | None:
        row = await self.session.scalar(
            select(TaskItemRow).where(
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.updated_by_run_id == run_id,
                TaskItemRow.updated_operation_key == operation_key,
                TaskItemRow.deleted_at.is_(None),
            )
        )
        return task_item_from_row(row) if row else None

    async def update(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        data: TaskItemUpdate,
        expected_row_version: int,
    ) -> TaskItem | None:
        values = {
            "updated_by_run_id": data.updated_by_run_id,
            "updated_operation_key": data.updated_operation_key,
            "row_version": TaskItemRow.row_version + 1,
            "updated_at": func.now(),
        }
        if data.title is not None:
            values["title"] = data.title
        if data.due_at is not None:
            values["due_at"] = data.due_at
        if data.status is not None:
            values["status"] = data.status.value
        row = await self.session.scalar(
            update(TaskItemRow)
            .where(
                TaskItemRow.id == task_id,
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.row_version == expected_row_version,
                TaskItemRow.deleted_at.is_(None),
            )
            .values(**values)
            .returning(TaskItemRow)
        )
        return task_item_from_row(row) if row else None

    async def update_from_ui(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        title: str,
        due_at: datetime | None,
        expected_row_version: int,
    ) -> TaskItem | None:
        row = await self.session.scalar(
            update(TaskItemRow)
            .where(
                TaskItemRow.id == task_id,
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.row_version == expected_row_version,
                TaskItemRow.deleted_at.is_(None),
            )
            .values(
                title=title,
                due_at=due_at,
                updated_by_run_id=None,
                updated_operation_key=None,
                row_version=TaskItemRow.row_version + 1,
                updated_at=func.now(),
            )
            .returning(TaskItemRow)
        )
        return task_item_from_row(row) if row else None

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> TaskItem | None:
        conditions = [
            TaskItemRow.tenant_id == context.tenant_id,
            TaskItemRow.owner_user_id == context.user_id,
            TaskItemRow.created_by_run_id == run_id,
            TaskItemRow.deleted_at.is_(None),
        ]
        if operation_key is not None:
            conditions.append(TaskItemRow.created_operation_key == operation_key)
        row = await self.session.scalar(select(TaskItemRow).where(*conditions))
        return task_item_from_row(row) if row else None

    async def set_status_from_ui(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        status: TaskStatus,
        expected_row_version: int,
    ) -> TaskItem | None:
        row = await self.session.scalar(
            update(TaskItemRow)
            .where(
                TaskItemRow.id == task_id,
                TaskItemRow.tenant_id == context.tenant_id,
                TaskItemRow.owner_user_id == context.user_id,
                TaskItemRow.row_version == expected_row_version,
                TaskItemRow.deleted_at.is_(None),
            )
            .values(
                status=status.value,
                updated_at=func.now(),
                updated_by_run_id=None,
                updated_operation_key=None,
                row_version=TaskItemRow.row_version + 1,
            )
            .returning(TaskItemRow)
        )
        return task_item_from_row(row) if row else None
