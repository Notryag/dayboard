from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal

from north import RuntimeStreamEvent


ScheduleKind = Literal["calendar", "task"]


@dataclass(frozen=True, slots=True)
class ProjectedStreamEvent:
    event_type: str
    data: dict[str, Any]


def project_runtime_stream_event(event: RuntimeStreamEvent) -> ProjectedStreamEvent | None:
    if (
        event.mode != "messages"
        or event.namespace
        or not isinstance(event.data, list)
        or not event.data
    ):
        return None
    message = event.data[0]
    if not isinstance(message, dict):
        return None

    message_type = message.get("type")
    tool_call_id = message.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id:
        if message_type != "tool":
            return None
        return _project_tool_message(message, tool_call_id)

    if message_type not in {"AIMessageChunk", "ai"}:
        return None
    content = message.get("content")
    if not isinstance(content, str) or not content:
        return None
    return ProjectedStreamEvent(
        "assistant_text_delta",
        {
            "message_id": _optional_text(message.get("id")),
            "delta": content,
        },
    )


def _project_tool_message(
    message: dict[str, Any],
    tool_call_id: str,
) -> ProjectedStreamEvent | None:
    content = message.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return None
    if not isinstance(content, dict):
        return None

    operation = content.get("type")
    tool_name = message.get("name")
    item_kind: ScheduleKind
    raw_item: Any
    expected_tools = {
        "calendar_entry_created": "create_calendar_entry",
        "calendar_entry_rescheduled": "reschedule_calendar_entry",
        "calendar_entry_cancelled": "cancel_calendar_entry",
        "task_item_created": "create_task_item",
        "task_item_updated": "update_task_item",
    }
    if expected_tools.get(operation) != tool_name:
        return None
    if operation in expected_tools and operation.startswith("calendar_entry_"):
        item_kind = "calendar"
        raw_item = content.get("calendar_entry")
    elif operation in expected_tools:
        item_kind = "task"
        raw_item = content.get("task_item")
    else:
        return None
    if not isinstance(raw_item, dict):
        return None

    item = _safe_calendar_item(raw_item) if item_kind == "calendar" else _safe_task_item(raw_item)
    if item is None:
        return None
    return ProjectedStreamEvent(
        "schedule_item_result",
        {
            "tool_call_id": tool_call_id,
            "operation": operation,
            "item": {"kind": item_kind, "value": item},
        },
    )


def _safe_calendar_item(item: dict[str, Any]) -> dict[str, Any] | None:
    required = ("id", "title", "start_time", "timezone", "status", "updated_at")
    if not all(key in item for key in required):
        return None
    return {
        key: item.get(key)
        for key in (
            "id",
            "title",
            "start_time",
            "end_time",
            "timezone",
            "participants",
            "reminder",
            "status",
            "created_by_run_id",
            "created_at",
            "updated_at",
        )
    }


def _safe_task_item(item: dict[str, Any]) -> dict[str, Any] | None:
    required = ("id", "title", "timezone", "status", "updated_at")
    if not all(key in item for key in required):
        return None
    return {
        key: item.get(key)
        for key in (
            "id",
            "title",
            "due_at",
            "timezone",
            "reminder",
            "status",
            "created_by_run_id",
            "created_at",
            "updated_at",
        )
    }


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
