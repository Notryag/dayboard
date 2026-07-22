from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from north import RuntimeStreamEvent
from pydantic import ValidationError

from dayboard.app.schedule_queries import CalendarEntryView, TaskItemView


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
    artifact = message.get("artifact")
    if not isinstance(artifact, dict):
        return None
    tool_name = message.get("name")
    artifact_type = artifact.get("type")
    if tool_name in {"search_calendar_entries", "search_task_items"}:
        if artifact_type != "schedule_items_result" or not isinstance(
            artifact.get("items"), list
        ):
            return None
        item_kind: ScheduleKind = "calendar" if tool_name == "search_calendar_entries" else "task"
        expected_operation = (
            "calendar_entry_found" if item_kind == "calendar" else "task_item_found"
        )
        if artifact.get("operation") != expected_operation:
            return None
        parts: list[dict[str, Any]] = []
        for raw_item in artifact["items"]:
            if (
                not isinstance(raw_item, dict)
                or raw_item.get("kind") != item_kind
                or not isinstance(raw_item.get("value"), dict)
            ):
                continue
            item = (
                _safe_calendar_item(raw_item["value"])
                if item_kind == "calendar"
                else _safe_task_item(raw_item["value"])
            )
            if item is None:
                continue
            parts.append(
                {
                    "tool_call_id": tool_call_id,
                    "operation": expected_operation,
                    "item": {"kind": item_kind, "value": item},
                }
            )
        return ProjectedStreamEvent(
            "schedule_items_result",
            {"tool_call_id": tool_call_id, "parts": parts},
        )

    if artifact_type != "schedule_item_result":
        return None

    operation = artifact.get("operation")
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
    elif operation in expected_tools:
        item_kind = "task"
    else:
        return None
    item_artifact = artifact.get("item")
    if not isinstance(item_artifact, dict) or item_artifact.get("kind") != item_kind:
        return None
    raw_item = item_artifact.get("value")
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
    try:
        validated = CalendarEntryView.model_validate(item)
    except ValidationError:
        return None
    return validated.model_dump(mode="json")


def _safe_task_item(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        validated = TaskItemView.model_validate(item)
    except ValidationError:
        return None
    return validated.model_dump(mode="json")


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
