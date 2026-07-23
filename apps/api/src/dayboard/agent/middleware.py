from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


ToolDomain = Literal["calendar", "task"]

CALENDAR_TOOLS = frozenset(
    {
        "create_calendar_entry",
        "search_calendar_entries",
        "reschedule_calendar_entry",
        "cancel_calendar_entry",
    }
)
TASK_TOOLS = frozenset(
    {
        "create_task_item",
        "search_task_items",
        "update_task_item",
    }
)
INTERACTION_TOOLS = frozenset({"ask_clarification"})
TERMINAL_WRITE_RESULTS = {
    "create_calendar_entry": "calendar_entry_created",
    "reschedule_calendar_entry": "calendar_entry_rescheduled",
    "cancel_calendar_entry": "calendar_entry_cancelled",
    "create_task_item": "task_item_created",
    "update_task_item": "task_item_updated",
}
SEARCH_TOOLS = frozenset({"search_calendar_entries", "search_task_items"})
MODEL_TIMEZONE = ZoneInfo("Asia/Shanghai")
ABSOLUTE_TO_LOCAL_FIELDS = {
    "start_time": "local_start",
    "end_time": "local_end",
    "due_at": "local_due",
}
MODEL_HIDDEN_FIELDS = {
    "timezone",
    "created_at",
    "updated_at",
    "created_by_run_id",
    "updated_by_run_id",
    "cancelled_by_run_id",
}


@dataclass(frozen=True, slots=True)
class _ToolResult:
    name: str
    domain: ToolDomain
    terminal: bool


class SchedulingToolBindingMiddleware(AgentMiddleware):
    """Bind the scheduling tool subset implied by canonical tool results."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        prepared = self._prepare_request(request)
        completion = _terminal_completion(prepared.messages)
        return AIMessage(content=completion) if completion is not None else handler(prepared)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        prepared = self._prepare_request(request)
        completion = _terminal_completion(prepared.messages)
        return (
            AIMessage(content=completion)
            if completion is not None
            else await handler(prepared)
        )

    def _prepare_request(self, request: ModelRequest) -> ModelRequest:
        request = _sanitize_model_messages(request)
        trailing = _trailing_tool_messages(request.messages)
        if not trailing:
            return request
        results = _parse_results(trailing)
        if results is None:
            if _invalid_result_count(request.messages) > 1:
                return request.override(tools=[])
            return request

        domains = {result.domain for result in results}
        if len(domains) != 1:
            return request
        if all(result.terminal for result in results):
            return request.override(tools=[])

        domain = next(iter(domains))
        allowed = (CALENDAR_TOOLS if domain == "calendar" else TASK_TOOLS) | INTERACTION_TOOLS
        return request.override(
            tools=[tool for tool in request.tools if getattr(tool, "name", None) in allowed]
        )


def _sanitize_model_messages(request: ModelRequest) -> ModelRequest:
    """Strip presentation artifacts and rewrite legacy UTC receipts for the provider."""
    changed = False
    messages: list[Any] = []
    for message in request.messages:
        if not isinstance(message, ToolMessage):
            messages.append(message)
            continue
        content = message.content
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                pass
            else:
                sanitized = _sanitize_receipt_value(payload)
                content = json.dumps(
                    sanitized,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
        artifact = getattr(message, "artifact", None)
        if content != message.content or artifact is not None:
            changed = True
            messages.append(message.model_copy(update={"content": content, "artifact": None}))
        else:
            messages.append(message)
    return request.override(messages=messages) if changed else request


def _sanitize_receipt_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_sanitize_receipt_value(item) for item in value]
    if not isinstance(value, dict):
        return value

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key in MODEL_HIDDEN_FIELDS:
            continue
        local_key = ABSOLUTE_TO_LOCAL_FIELDS.get(key)
        if local_key is not None and isinstance(item, str):
            local_value = _absolute_to_local_minute(item)
            if local_value is not None:
                sanitized[local_key] = local_value
                continue
        sanitized[key] = _sanitize_receipt_value(item)
    return sanitized


def _absolute_to_local_minute(value: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.isoformat(timespec="minutes")
    return (
        parsed.astimezone(MODEL_TIMEZONE)
        .replace(tzinfo=None)
        .isoformat(timespec="minutes")
    )


def _trailing_tool_messages(messages: Sequence[Any]) -> list[ToolMessage]:
    trailing: list[ToolMessage] = []
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            break
        trailing.append(message)
    return trailing


def _parse_results(messages: Sequence[ToolMessage]) -> list[_ToolResult] | None:
    parsed: list[_ToolResult] = []
    for message in messages:
        result = _parse_result(message)
        if result is None:
            return None
        parsed.append(result)
    return parsed


def _terminal_completion(messages: Sequence[Any]) -> str | None:
    trailing = _trailing_tool_messages(messages)
    results = _parse_results(trailing)
    if not results or not all(result.terminal for result in results):
        return None

    payloads = [_tool_payload(message) for message in trailing]
    if any(payload is None for payload in payloads):
        return None
    terminal_payloads = [payload for payload in payloads if payload is not None]
    conflict_count = sum(
        len(conflicts)
        for payload in terminal_payloads
        if isinstance((conflicts := payload.get("conflicts")), list)
    )
    if len(terminal_payloads) > 1:
        completion = f"已完成 {len(terminal_payloads)} 项安排。"
    else:
        completion = _single_terminal_completion(terminal_payloads[0])
    if conflict_count:
        return f"{completion[:-1]}，检测到 {conflict_count} 项时间冲突。"
    return completion


def _single_terminal_completion(payload: dict[str, Any]) -> str:
    result_type = payload.get("type")
    if result_type == "calendar_entry_created":
        return "日程已创建。"
    if result_type == "calendar_entry_rescheduled":
        return "日程已更新。"
    if result_type == "calendar_entry_cancelled":
        return "日程已取消。"
    if result_type == "task_item_created":
        return "待办已创建。"
    task = payload.get("task_item")
    status = task.get("status") if isinstance(task, dict) else None
    if status == "completed":
        return "待办已完成。"
    if status == "cancelled":
        return "待办已取消。"
    return "待办已更新。"


def _invalid_result_count(messages: Sequence[Any]) -> int:
    count = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage) and _parse_result(message) is None:
            count += 1
    return count


def _parse_result(message: ToolMessage) -> _ToolResult | None:
    if getattr(message, "status", "success") == "error":
        return None
    name = message.name or ""
    domain = _tool_domain(name)
    if domain is None or not isinstance(message.content, str):
        return None
    payload = _tool_payload(message)
    if payload is None:
        return None

    if name in SEARCH_TOOLS:
        return _ToolResult(name=name, domain=domain, terminal=False) if isinstance(payload, list) else None

    expected_type = TERMINAL_WRITE_RESULTS.get(name)
    if expected_type is None or not isinstance(payload, dict):
        return None
    if payload.get("type") != expected_type:
        return None
    return _ToolResult(name=name, domain=domain, terminal=True)


def _tool_payload(message: ToolMessage) -> dict[str, Any] | list[Any] | None:
    if not isinstance(message.content, str):
        return None
    try:
        payload = json.loads(message.content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, (dict, list)) else None


def _tool_domain(name: str) -> ToolDomain | None:
    if name in CALENDAR_TOOLS:
        return "calendar"
    if name in TASK_TOOLS:
        return "task"
    return None
