from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.scheduling import calendar_entry_from_row, task_item_from_row
from dayboard.context import TenantContext
from dayboard.db.repositories import CalendarEntryRepository, TaskItemRepository
from dayboard.domain.calendar import CalendarEntry, Reminder
from dayboard.domain.tasks import TaskItem, TaskStatus


class InvalidScheduleCursor(ValueError):
    pass


class CalendarEntryView(BaseModel):
    id: UUID
    title: str
    start_time: datetime
    end_time: datetime | None
    timezone: str
    participants: list[str]
    reminder: Reminder | None
    status: Literal["scheduled", "cancelled"]
    created_by_run_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, entry: CalendarEntry) -> CalendarEntryView:
        return cls.model_validate(
            {
                **entry.model_dump(),
                "status": "cancelled" if entry.cancelled_at is not None else "scheduled",
            }
        )


class TaskItemView(BaseModel):
    id: UUID
    title: str
    due_at: datetime | None
    timezone: str
    reminder: Reminder | None
    status: TaskStatus
    created_by_run_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, task: TaskItem) -> TaskItemView:
        return cls.model_validate(task, from_attributes=True)


ItemT = TypeVar("ItemT")


class SchedulePage(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    next_cursor: str | None = None


class RunScheduleItemGroup(BaseModel):
    run_id: UUID
    calendar_entries: list[CalendarEntryView]
    task_items: list[TaskItemView]


def _encode_cursor(payload: dict[str, str | bool | None]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str, expected_kind: str) -> dict:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if not isinstance(payload, dict) or payload.get("kind") != expected_kind:
            raise ValueError
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError) as exc:
        raise InvalidScheduleCursor("Invalid pagination cursor") from exc


def _cursor_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise InvalidScheduleCursor("Invalid pagination cursor")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidScheduleCursor("Invalid pagination cursor") from exc
    if parsed.utcoffset() is None:
        raise InvalidScheduleCursor("Invalid pagination cursor")
    return parsed


class ScheduleQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self.calendar_entries = CalendarEntryRepository(session)
        self.task_items = TaskItemRepository(session)

    async def list_calendar_entries(
        self,
        context: TenantContext,
        *,
        start_time: datetime | None,
        end_time: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> SchedulePage[CalendarEntryView]:
        cursor_start = None
        cursor_id = None
        if cursor:
            payload = _decode_cursor(cursor, "calendar")
            try:
                cursor_start = _cursor_datetime(payload["start_time"])
                cursor_id = UUID(payload["id"])
            except (KeyError, TypeError, ValueError, InvalidScheduleCursor) as exc:
                raise InvalidScheduleCursor("Invalid pagination cursor") from exc
        rows = await self.calendar_entries.list_page(
            context,
            start_time=start_time,
            end_time=end_time,
            cursor_start_time=cursor_start,
            cursor_id=cursor_id,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = None
        if has_more:
            last = page_rows[-1]
            next_cursor = _encode_cursor(
                {"kind": "calendar", "start_time": last.start_time.isoformat(), "id": str(last.id)}
            )
        return SchedulePage(
            items=[CalendarEntryView.from_domain(calendar_entry_from_row(row)) for row in page_rows],
            next_cursor=next_cursor,
        )

    async def list_task_items(
        self,
        context: TenantContext,
        *,
        status: TaskStatus | None,
        due_kind: Literal["all", "dated", "undated"],
        due_from: datetime | None,
        due_to: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> SchedulePage[TaskItemView]:
        cursor_due = None
        cursor_created = None
        cursor_id = None
        cursor_has_due = None
        if cursor:
            payload = _decode_cursor(cursor, "task")
            try:
                cursor_has_due = payload["has_due_at"]
                if not isinstance(cursor_has_due, bool):
                    raise InvalidScheduleCursor("Invalid pagination cursor")
                cursor_due = (
                    _cursor_datetime(payload["due_at"]) if cursor_has_due else None
                )
                cursor_created = _cursor_datetime(payload["created_at"])
                cursor_id = UUID(payload["id"])
            except (KeyError, TypeError, ValueError, InvalidScheduleCursor) as exc:
                raise InvalidScheduleCursor("Invalid pagination cursor") from exc
        rows = await self.task_items.list_page(
            context,
            status=status,
            due_kind=due_kind,
            due_from=due_from,
            due_to=due_to,
            cursor_due_at=cursor_due,
            cursor_created_at=cursor_created,
            cursor_id=cursor_id,
            cursor_has_due_at=cursor_has_due,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = None
        if has_more:
            last = page_rows[-1]
            next_cursor = _encode_cursor(
                {
                    "kind": "task",
                    "has_due_at": last.due_at is not None,
                    "due_at": last.due_at.isoformat() if last.due_at else None,
                    "created_at": last.created_at.isoformat(),
                    "id": str(last.id),
                }
            )
        return SchedulePage(
            items=[TaskItemView.from_domain(task_item_from_row(row)) for row in page_rows],
            next_cursor=next_cursor,
        )

    async def list_created_by_runs(
        self,
        context: TenantContext,
        run_ids: list[UUID],
    ) -> list[RunScheduleItemGroup]:
        unique_run_ids = list(dict.fromkeys(run_ids))
        calendar_rows = await self.calendar_entries.list_created_by_runs(context, unique_run_ids)
        task_rows = await self.task_items.list_created_by_runs(context, unique_run_ids)
        calendars_by_run: dict[UUID, list[CalendarEntryView]] = {
            run_id: [] for run_id in unique_run_ids
        }
        tasks_by_run: dict[UUID, list[TaskItemView]] = {
            run_id: [] for run_id in unique_run_ids
        }
        for row in calendar_rows:
            if row.created_by_run_id in calendars_by_run:
                calendars_by_run[row.created_by_run_id].append(
                    CalendarEntryView.from_domain(calendar_entry_from_row(row))
                )
        for row in task_rows:
            if row.created_by_run_id in tasks_by_run:
                tasks_by_run[row.created_by_run_id].append(
                    TaskItemView.from_domain(task_item_from_row(row))
                )
        return [
            RunScheduleItemGroup(
                run_id=run_id,
                calendar_entries=calendars_by_run[run_id],
                task_items=tasks_by_run[run_id],
            )
            for run_id in unique_run_ids
            if calendars_by_run[run_id] or tasks_by_run[run_id]
        ]
