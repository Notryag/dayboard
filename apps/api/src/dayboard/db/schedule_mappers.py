"""Translate SQLAlchemy schedule records into product domain objects."""

from __future__ import annotations

from dayboard.db.models import CalendarEntryRow, TaskItemRow
from dayboard.domain.calendar import CalendarEntry, Reminder
from dayboard.domain.tasks import TaskItem, TaskStatus


def calendar_entry_from_row(row: CalendarEntryRow) -> CalendarEntry:
    return CalendarEntry(
        id=row.id,
        row_version=row.row_version,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        timing_kind=row.timing_kind,
        scheduled_date=row.scheduled_date,
        start_time=row.start_time,
        end_time=row.end_time,
        timezone=row.timezone,
        participants=row.participants,
        reminder=Reminder.model_validate(row.reminder) if row.reminder else None,
        created_by_run_id=row.created_by_run_id,
        created_operation_key=row.created_operation_key,
        updated_by_run_id=row.updated_by_run_id,
        updated_operation_key=row.updated_operation_key,
        cancelled_by_run_id=row.cancelled_by_run_id,
        cancelled_operation_key=row.cancelled_operation_key,
        cancellation_reason=row.cancellation_reason,
        cancelled_at=row.deleted_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def task_item_from_row(row: TaskItemRow) -> TaskItem:
    return TaskItem(
        id=row.id,
        row_version=row.row_version,
        tenant_id=row.tenant_id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        due_at=row.due_at,
        timezone=row.timezone,
        reminder=Reminder.model_validate(row.reminder) if row.reminder else None,
        status=TaskStatus(row.status),
        created_by_run_id=row.created_by_run_id,
        created_operation_key=row.created_operation_key,
        updated_by_run_id=row.updated_by_run_id,
        updated_operation_key=row.updated_operation_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
