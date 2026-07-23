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


def _write_result(
    name: str,
    result_type: str,
    *,
    status: str = "success",
    **payload,
) -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"type": result_type, **payload}),
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


def test_async_wrapper_completes_terminal_write_without_calling_model() -> None:
    async def run() -> tuple[AIMessage, bool]:
        middleware = SchedulingToolBindingMiddleware()
        request = _request([_write_result("update_task_item", "task_item_updated")])
        called = False

        async def handler(prepared):
            nonlocal called
            called = True
            return prepared.tools

        response = await middleware.awrap_model_call(request, handler)
        return response, called

    response, called = asyncio.run(run())

    assert isinstance(response, AIMessage)
    assert response.content == "待办已更新。"
    assert called is False


def test_mixed_terminal_batch_completes_without_calling_model() -> None:
    middleware = SchedulingToolBindingMiddleware()
    request = _request(
        [
            _write_result("create_calendar_entry", "calendar_entry_created"),
            _write_result("create_task_item", "task_item_created"),
        ]
    )

    def handler(prepared):
        raise AssertionError(f"model should not be called with {prepared.tools}")

    response = middleware.wrap_model_call(request, handler)

    assert isinstance(response, AIMessage)
    assert response.content == "已完成 2 项安排。"


def test_terminal_completion_preserves_conflict_warning() -> None:
    middleware = SchedulingToolBindingMiddleware()
    request = _request(
        [
            _write_result(
                "create_calendar_entry",
                "calendar_entry_created",
                conflicts=[{"id": "conflict-1"}],
            )
        ]
    )

    response = middleware.wrap_model_call(request, lambda prepared: prepared)

    assert isinstance(response, AIMessage)
    assert response.content == "日程已创建，检测到 1 项时间冲突。"


def test_search_and_error_results_still_call_model() -> None:
    middleware = SchedulingToolBindingMiddleware()
    search_called = False
    error_called = False

    def search_handler(prepared):
        nonlocal search_called
        search_called = True
        return AIMessage(content="继续处理")

    def error_handler(prepared):
        nonlocal error_called
        error_called = True
        return AIMessage(content="说明错误")

    search_response = middleware.wrap_model_call(
        _request([_search_result("search_calendar_entries")]), search_handler
    )
    error_response = middleware.wrap_model_call(
        _request(
            [
                _write_result(
                    "create_calendar_entry",
                    "calendar_entry_created",
                    status="error",
                )
            ]
        ),
        error_handler,
    )

    assert search_response.content == "继续处理"
    assert error_response.content == "说明错误"
    assert search_called is True
    assert error_called is True


def test_provider_request_strips_artifact_and_rewrites_legacy_utc_receipt() -> None:
    middleware = SchedulingToolBindingMiddleware()
    original = ToolMessage(
        content=json.dumps(
            {
                "type": "calendar_entry_created",
                "calendar_entry": {
                    "id": "entry-1",
                    "title": "钓鱼",
                    "start_time": "2026-07-24T08:00:00+00:00",
                    "end_time": "2026-07-24T09:00:00+00:00",
                    "timezone": "Asia/Shanghai",
                    "updated_at": "2026-07-23T08:00:00+00:00",
                },
            }
        ),
        artifact={
            "item": {
                "value": {"start_time": "2026-07-24T08:00:00+00:00"}
            }
        },
        tool_call_id="call-create",
        name="create_calendar_entry",
    )

    prepared = middleware._prepare_request(_request([original]))
    provider_message = prepared.messages[0]
    payload = json.loads(provider_message.content)

    assert original.artifact is not None
    assert provider_message.artifact is None
    assert payload["calendar_entry"]["local_start"] == "2026-07-24T16:00"
    assert payload["calendar_entry"]["local_end"] == "2026-07-24T17:00"
    assert "start_time" not in provider_message.content
    assert "end_time" not in provider_message.content
    assert "timezone" not in provider_message.content
    assert "updated_at" not in provider_message.content
