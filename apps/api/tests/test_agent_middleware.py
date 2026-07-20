import asyncio
import json
from types import SimpleNamespace

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from dayboard.agent.middleware import SchedulingToolBindingMiddleware


TOOL_NAMES = [
    "create_calendar_entry",
    "search_calendar_entries",
    "reschedule_calendar_entry",
    "cancel_calendar_entry",
    "create_task_item",
    "search_task_items",
    "update_task_item",
    "ask_clarification",
]


def _tools():
    return [SimpleNamespace(name=name) for name in TOOL_NAMES]


def _request(messages) -> ModelRequest:
    return ModelRequest(model=object(), messages=messages, tools=_tools())


def _write_result(name: str, result_type: str, *, status: str = "success") -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"type": result_type}),
        tool_call_id=f"call-{name}",
        name=name,
        status=status,
    )


def _search_result(name: str) -> ToolMessage:
    return ToolMessage(content="[]", tool_call_id=f"call-{name}", name=name)


def _names(request: ModelRequest) -> list[str]:
    return [tool.name for tool in request.tools]


def test_terminal_single_domain_writes_remove_tools() -> None:
    middleware = SchedulingToolBindingMiddleware()
    request = _request(
        [_write_result("create_calendar_entry", "calendar_entry_created")]
    )

    assert middleware._prepare_request(request).tools == []


def test_mixed_domain_batch_retains_full_surface() -> None:
    middleware = SchedulingToolBindingMiddleware()
    request = _request(
        [
            _write_result("create_calendar_entry", "calendar_entry_created"),
            _write_result("create_task_item", "task_item_created"),
        ]
    )

    assert _names(middleware._prepare_request(request)) == TOOL_NAMES


def test_successful_search_narrows_to_domain_and_clarification() -> None:
    middleware = SchedulingToolBindingMiddleware()

    calendar = middleware._prepare_request(
        _request([_search_result("search_calendar_entries")])
    )
    task = middleware._prepare_request(_request([_search_result("search_task_items")]))

    assert _names(calendar) == [
        "create_calendar_entry",
        "search_calendar_entries",
        "reschedule_calendar_entry",
        "cancel_calendar_entry",
        "ask_clarification",
    ]
    assert _names(task) == [
        "create_task_item",
        "search_task_items",
        "update_task_item",
        "ask_clarification",
    ]


def test_error_or_malformed_result_restores_full_surface() -> None:
    middleware = SchedulingToolBindingMiddleware()
    error = _request(
        [
            _write_result(
                "create_calendar_entry",
                "calendar_entry_created",
                status="error",
            )
        ]
    )
    malformed = _request(
        [ToolMessage(content="{}", tool_call_id="search", name="search_task_items")]
    )

    assert _names(middleware._prepare_request(error)) == TOOL_NAMES
    assert _names(middleware._prepare_request(malformed)) == TOOL_NAMES


def test_second_failure_in_one_user_turn_stops_tool_retries() -> None:
    middleware = SchedulingToolBindingMiddleware()
    first_error = _write_result(
        "create_calendar_entry", "calendar_entry_created", status="error"
    )
    second_error = _write_result(
        "create_calendar_entry", "calendar_entry_created", status="error"
    )
    request = _request(
        [
            HumanMessage(content="安排会议"),
            AIMessage(content=""),
            first_error,
            AIMessage(content="正在重试"),
            second_error,
        ]
    )

    assert middleware._prepare_request(request).tools == []


def test_new_user_turn_restores_full_surface() -> None:
    middleware = SchedulingToolBindingMiddleware()
    request = _request(
        [
            _write_result("create_task_item", "task_item_created"),
            AIMessage(content="已添加"),
            HumanMessage(content="再加一个"),
        ]
    )

    assert _names(middleware._prepare_request(request)) == TOOL_NAMES


def test_async_wrapper_uses_the_same_binding_policy() -> None:
    async def run() -> list:
        middleware = SchedulingToolBindingMiddleware()
        request = _request([_write_result("update_task_item", "task_item_updated")])

        async def handler(prepared):
            return prepared.tools

        return await middleware.awrap_model_call(request, handler)

    assert asyncio.run(run()) == []
