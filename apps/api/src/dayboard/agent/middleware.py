from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

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
        return handler(self._prepare_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        return await handler(self._prepare_request(request))

    def _prepare_request(self, request: ModelRequest) -> ModelRequest:
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
    try:
        payload = json.loads(message.content)
    except json.JSONDecodeError:
        return None

    if name in SEARCH_TOOLS:
        return _ToolResult(name=name, domain=domain, terminal=False) if isinstance(payload, list) else None

    expected_type = TERMINAL_WRITE_RESULTS.get(name)
    if expected_type is None or not isinstance(payload, dict):
        return None
    if payload.get("type") != expected_type:
        return None
    return _ToolResult(name=name, domain=domain, terminal=True)


def _tool_domain(name: str) -> ToolDomain | None:
    if name in CALENDAR_TOOLS:
        return "calendar"
    if name in TASK_TOOLS:
        return "task"
    return None
