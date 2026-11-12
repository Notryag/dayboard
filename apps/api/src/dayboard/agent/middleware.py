from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage


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
RUNTIME_CONTEXT_MARKER = "dayboard_runtime_context"


class SchedulingToolBindingMiddleware(AgentMiddleware):
    """Keep all domains available and bound consecutive failed tool rounds."""

    def __init__(self, *, runtime_context: str | None = None) -> None:
        self.runtime_context = runtime_context

    def wrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]
    ) -> ModelResponse:
        return handler(self._prepare_request(request))

    async def awrap_model_call(
        self, request: ModelRequest, handler: Callable[[ModelRequest], Awaitable[ModelResponse]]
    ) -> ModelResponse:
        return await handler(self._prepare_request(request))

    def _prepare_request(self, request: ModelRequest) -> ModelRequest:
        request = _sanitize_model_messages(request)
        request = _inject_runtime_context(request, self.runtime_context)
        if _consecutive_failed_rounds(request.messages) >= 2:
            return request.override(
                tools=[],
                messages=[
                    *request.messages,
                    SystemMessage(
                        content="Tool recovery failed twice. Explain completed and unresolved actions "
                        "accurately from receipts; do not claim the entire request succeeded."
                    ),
                ],
            )
        return request


def _inject_runtime_context(
    request: ModelRequest,
    runtime_context: str | None,
) -> ModelRequest:
    if not runtime_context:
        return request

    messages = [
        message
        for message in request.messages
        if not (
            isinstance(message, SystemMessage)
            and message.additional_kwargs.get(RUNTIME_CONTEXT_MARKER) is True
        )
    ]
    current_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        None,
    )
    if current_user_index is None:
        return request

    messages.insert(
        current_user_index,
        SystemMessage(
            content=runtime_context,
            additional_kwargs={RUNTIME_CONTEXT_MARKER: True},
        ),
    )
    return request.override(messages=messages)


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
    return parsed.astimezone(MODEL_TIMEZONE).replace(tzinfo=None).isoformat(timespec="minutes")


def _consecutive_failed_rounds(messages: Sequence[Any]) -> int:
    # One model tool batch is one attempt, regardless of how many calls failed.
    # A fully successful batch ends the recovery episode; a new user resets it.
    rounds = 0
    batch: list[ToolMessage] = []
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            batch.append(message)
            continue
        if batch:
            if not any(_failed_result(item) for item in batch):
                return rounds
            rounds += 1
            batch = []
        if isinstance(message, HumanMessage):
            break
    if batch and any(_failed_result(item) for item in batch):
        rounds += 1
    return rounds


def _failed_result(message: ToolMessage) -> bool:
    if message.status == "error":
        return True
    if message.name in INTERACTION_TOOLS:
        return False
    if not isinstance(message.content, str) or message.name is None:
        return True
    try:
        payload = json.loads(message.content)
    except (TypeError, json.JSONDecodeError):
        return True
    if message.name in SEARCH_TOOLS:
        return not (
            isinstance(payload, dict)
            and isinstance(payload.get("items"), list)
            and isinstance(payload.get("has_more"), bool)
        )
    expected = TERMINAL_WRITE_RESULTS.get(message.name)
    return expected is None or not isinstance(payload, dict) or payload.get("type") != expected
