from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, ToolMessage


TERMINAL_WRITE_RESULTS = {
    "create_calendar_entry": "calendar_entry_created",
    "reschedule_calendar_entry": "calendar_entry_rescheduled",
    "cancel_calendar_entry": "calendar_entry_cancelled",
    "create_task_item": "task_item_created",
    "update_task_item": "task_item_updated",
}


class TerminalWriteToolPruningMiddleware(AgentMiddleware):
    """Omit tool schemas from the final response round after successful writes."""

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
        if _has_only_terminal_write_results(request.messages):
            return request.override(tools=[])
        return request


def _has_only_terminal_write_results(messages: list[Any]) -> bool:
    trailing_results: list[ToolMessage] = []
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            break
        trailing_results.append(message)

    if not trailing_results:
        return False
    return all(_is_terminal_write_result(message) for message in trailing_results)


def _is_terminal_write_result(message: ToolMessage) -> bool:
    if getattr(message, "status", "success") == "error":
        return False
    expected_result = TERMINAL_WRITE_RESULTS.get(message.name or "")
    if expected_result is None:
        return False
    content = message.content
    if not isinstance(content, str):
        return False
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and payload.get("type") == expected_result
