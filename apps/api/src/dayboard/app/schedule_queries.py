from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime, time, timedelta
import json
from typing import Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.scheduling import calendar_entry_from_row, task_item_from_row
from agent_platform.core import TenantContext
from dayboard.db.repositories import CalendarEntryRepository, TaskItemRepository
from dayboard.domain.calendar import CalendarEntry, CalendarTimingKind, Reminder
from dayboard.domain.tasks import TaskItem, TaskStatus


class InvalidScheduleCursor(ValueError):
    pass


class CalendarEntryView(BaseModel):
    id: UUID
    row_version: int
    title: str
    timing_kind: CalendarTimingKind
    scheduled_date: date | None
    start_time: datetime | None
    end_time: datetime | None
    timezone: str
    participants: list[str]
    reminder: Reminder | None
    status: Literal["scheduled", "completed", "cancelled"]
    created_by_run_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, entry: CalendarEntry) -> CalendarEntryView:
        return cls.model_validate(
            {
                **entry.model_dump(),
                "status": (
                    "cancelled"
                    if entry.cancelled_at is not None
                    else "completed"
                    if entry.completed_at is not None
                    else "scheduled"
                ),
            }
        )


class TaskItemView(BaseModel):
    id: UUID
    row_version: int
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


def _exclusive_local_end_date(value: datetime, timezone: str) -> date:
    local = value.astimezone(ZoneInfo(timezone))
    if local.timetz().replace(tzinfo=None) == time.min:
        return local.date()
    return local.date() + timedelta(days=1)


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
            start_date=(
                start_time.astimezone(ZoneInfo(context.timezone)).date() if start_time else None
            ),
            end_date=(
                _exclusive_local_end_date(end_time, context.timezone) if end_time else None
            ),
            cursor_start_time=cursor_start,
            cursor_id=cursor_id,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = None
        if has_more:
            last = page_rows[-1]
            cursor_time = last.start_time or datetime.combine(
                last.scheduled_date, time.min, tzinfo=UTC
            )
            next_cursor = _encode_cursor(
                {"kind": "calendar", "start_time": cursor_time.isoformat(), "id": str(last.id)}
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
