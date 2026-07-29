from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field, model_validator


BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")
MAX_SCHEDULE_PAGES = 20


class ExpectedScheduleItem(BaseModel):
    kind: Literal["calendar", "task"]
    title: str = Field(min_length=1, max_length=240)
    status: Literal["scheduled", "open", "completed", "cancelled"] | None = None
    timing_kind: Literal["timed", "anytime"] | None = None
    scheduled_date: str | None = None
    local_start: str | None = None
    local_end: str | None = None
    due_local: str | None = None
    count: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> ExpectedScheduleItem:
        calendar_fields = (
            self.timing_kind,
            self.scheduled_date,
            self.local_start,
            self.local_end,
        )
        if self.kind == "calendar" and self.due_local is not None:
            raise ValueError("calendar expectations cannot define due_local")
        if self.kind == "task" and any(value is not None for value in calendar_fields):
            raise ValueError("task expectations cannot define calendar timing fields")
        return self


@dataclass(frozen=True, slots=True)
class EvalTemplateContext:
    today: str
    tomorrow: str
    day_after_tomorrow: str
    future_date: str
    future_month_day_zh: str

    @classmethod
    def capture(cls, *, now: datetime | None = None) -> EvalTemplateContext:
        local_now = now or datetime.now(BEIJING_TIMEZONE)
        if local_now.tzinfo is None:
            local_now = local_now.replace(tzinfo=BEIJING_TIMEZONE)
        else:
            local_now = local_now.astimezone(BEIJING_TIMEZONE)
        today = local_now.date()
        future_date = today + timedelta(days=30)
        return cls(
            today=today.isoformat(),
            tomorrow=(today + timedelta(days=1)).isoformat(),
            day_after_tomorrow=(today + timedelta(days=2)).isoformat(),
            future_date=future_date.isoformat(),
            future_month_day_zh=f"{future_date.month}月{future_date.day}号",
        )

    def variables(self, *, tag: str) -> dict[str, str]:
        return {
            "tag": tag,
            "today": self.today,
            "tomorrow": self.tomorrow,
            "day_after_tomorrow": self.day_after_tomorrow,
            "future_date": self.future_date,
            "future_month_day_zh": self.future_month_day_zh,
        }


def render_template(value: str, variables: dict[str, str]) -> str:
    try:
        return value.format_map(variables)
    except KeyError as exc:
        raise ValueError(f"unknown Eval template variable: {exc.args[0]}") from exc


def render_expectation(
    expectation: ExpectedScheduleItem,
    variables: dict[str, str],
) -> ExpectedScheduleItem:
    payload = expectation.model_dump()
    for field, value in payload.items():
        if isinstance(value, str):
            payload[field] = render_template(value, variables)
    return ExpectedScheduleItem.model_validate(payload)


def _local_minute(value: object, timezone: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError(f"schedule API returned a naive datetime: {value}")
    zone = ZoneInfo(timezone) if isinstance(timezone, str) else BEIJING_TIMEZONE
    return parsed.astimezone(zone).replace(tzinfo=None).isoformat(timespec="minutes")


def _snapshot(kind: Literal["calendar", "task"], item: dict[str, Any]) -> dict[str, Any]:
    common = {
        "kind": kind,
        "id": item.get("id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "created_by_run_id": item.get("created_by_run_id"),
    }
    if kind == "calendar":
        return {
            **common,
            "timing_kind": item.get("timing_kind"),
            "scheduled_date": item.get("scheduled_date"),
            "local_start": _local_minute(item.get("start_time"), item.get("timezone")),
            "local_end": _local_minute(item.get("end_time"), item.get("timezone")),
        }
    return {
        **common,
        "due_local": _local_minute(item.get("due_at"), item.get("timezone")),
    }


def _query_params(expectation: ExpectedScheduleItem) -> dict[str, str | int]:
    if expectation.kind == "calendar":
        selected_date = expectation.scheduled_date
        if selected_date is None and expectation.local_start is not None:
            selected_date = expectation.local_start[:10]
        params: dict[str, str | int] = {"limit": 100}
        if selected_date is not None:
            params["date"] = selected_date
        return params

    params = {"limit": 100, "status": "all"}
    if expectation.due_local is not None:
        params["date"] = expectation.due_local[:10]
    else:
        params["due_kind"] = "all"
    return params


async def _list_schedule_items(
    client: httpx.AsyncClient,
    expectation: ExpectedScheduleItem,
) -> list[dict[str, Any]]:
    path = "/api/calendar-entries" if expectation.kind == "calendar" else "/api/task-items"
    params = _query_params(expectation)
    items: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(MAX_SCHEDULE_PAGES):
        request_params = {**params, **({"cursor": cursor} if cursor else {})}
        response = await client.get(path, params=request_params)
        response.raise_for_status()
        payload = response.json()
        page_items = payload.get("items")
        if not isinstance(page_items, list):
            raise ValueError(f"schedule API returned invalid items for {path}")
        items.extend(item for item in page_items if isinstance(item, dict))
        cursor = payload.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            return items
    raise ValueError(f"schedule API exceeded {MAX_SCHEDULE_PAGES} pages for one Eval assertion")


def _expected_fields(expectation: ExpectedScheduleItem) -> dict[str, Any]:
    payload = expectation.model_dump(exclude={"count"})
    return {key: value for key, value in payload.items() if value is not None}


async def evaluate_schedule_expectation(
    client: httpx.AsyncClient,
    expectation: ExpectedScheduleItem,
) -> dict[str, Any]:
    snapshots = [
        _snapshot(expectation.kind, item)
        for item in await _list_schedule_items(client, expectation)
        if item.get("title") == expectation.title
    ]
    expected_fields = _expected_fields(expectation)
    matching = [
        snapshot
        for snapshot in snapshots
        if all(snapshot.get(field) == value for field, value in expected_fields.items())
    ]
    passed = len(snapshots) == expectation.count and len(matching) == expectation.count
    return {
        "passed": passed,
        "expected": expectation.model_dump(),
        "matched_count": len(matching),
        "title_match_count": len(snapshots),
        "actual": snapshots,
    }


async def evaluate_schedule_expectations(
    client: httpx.AsyncClient,
    expectations: tuple[ExpectedScheduleItem, ...],
    variables: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        await evaluate_schedule_expectation(client, render_expectation(expectation, variables))
        for expectation in expectations
    ]
