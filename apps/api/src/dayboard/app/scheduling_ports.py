"""Storage-neutral contracts for Dayboard scheduling use cases."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

from agent_platform.core import TenantContext

from dayboard.domain.calendar import CalendarEntry, CalendarEntryCreate, CalendarTimingKind
from dayboard.domain.reminders import ReminderSourceType
from dayboard.domain.tasks import TaskItem, TaskItemCreate, TaskItemUpdate, TaskStatus


class CalendarEntryStore(Protocol):
    async def create(
        self,
        context: TenantContext,
        data: CalendarEntryCreate,
    ) -> CalendarEntry: ...

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
    ) -> Sequence[CalendarEntry]: ...

    async def search_active(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        start_date: date,
        end_date: date,
        title_query: str | None = None,
    ) -> Sequence[CalendarEntry]: ...

    async def get(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None: ...

    async def get_for_update(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None: ...

    async def get_including_cancelled(
        self,
        context: TenantContext,
        entry_id: UUID,
    ) -> CalendarEntry | None: ...

    async def get_by_updated_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None: ...

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
    ) -> CalendarEntry | None: ...

    async def get_by_cancelled_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> CalendarEntry | None: ...

    async def cancel(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
        cancelled_by_run_id: UUID,
        operation_key: str,
        cancellation_reason: str | None,
    ) -> CalendarEntry | None: ...

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> CalendarEntry | None: ...

    async def cancel_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None: ...

    async def complete_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None: ...

    async def reopen_from_ui(
        self,
        context: TenantContext,
        *,
        entry_id: UUID,
        expected_row_version: int,
    ) -> CalendarEntry | None: ...

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
    ) -> CalendarEntry | None: ...

    async def list_overlapping(
        self,
        context: TenantContext,
        *,
        start_time: datetime,
        end_time: datetime,
        default_duration: timedelta,
        exclude_entry_id: UUID | None = None,
    ) -> Sequence[CalendarEntry]: ...


class TaskItemStore(Protocol):
    async def create(self, context: TenantContext, data: TaskItemCreate) -> TaskItem: ...

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
    ) -> Sequence[TaskItem]: ...

    async def search(
        self,
        context: TenantContext,
        *,
        title_query: str | None = None,
        status: TaskStatus | None = TaskStatus.open,
    ) -> Sequence[TaskItem]: ...

    async def get(
        self,
        context: TenantContext,
        task_id: UUID,
    ) -> TaskItem | None: ...

    async def get_by_updated_operation(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str,
    ) -> TaskItem | None: ...

    async def update(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        data: TaskItemUpdate,
        expected_row_version: int,
    ) -> TaskItem | None: ...

    async def update_from_ui(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        title: str,
        due_at: datetime | None,
        expected_row_version: int,
    ) -> TaskItem | None: ...

    async def get_by_created_run(
        self,
        context: TenantContext,
        run_id: UUID,
        operation_key: str | None = None,
    ) -> TaskItem | None: ...

    async def set_status_from_ui(
        self,
        context: TenantContext,
        *,
        task_id: UUID,
        status: TaskStatus,
        expected_row_version: int,
    ) -> TaskItem | None: ...


class ReminderScheduleStore(Protocol):
    async def replace_pending(
        self,
        context: TenantContext,
        *,
        source_type: ReminderSourceType,
        source_id: UUID,
        scheduled_for: datetime | None,
        payload: dict[str, object] | None = None,
        channel: str = "in_app",
    ) -> None: ...


class ScheduleStores(Protocol):
    calendar_entries: CalendarEntryStore
    task_items: TaskItemStore


class SchedulingUnitOfWork(ScheduleStores, Protocol):
    """Scheduling stores that participate in one atomic transaction."""

    reminders: ReminderScheduleStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
