import asyncio
import json
from types import SimpleNamespace

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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
    return ToolMessage(
        content='{"items": [], "has_more": false}', tool_call_id=f"call-{name}", name=name
    )


def _names(request: ModelRequest) -> list[str]:
    return [tool.name for tool in request.tools]


def test_search_and_writes_preserve_every_domain() -> None:
    middleware = SchedulingToolBindingMiddleware()
    for result in [
        _search_result("search_calendar_entries"),
        _search_result("search_task_items"),
        _write_result("create_calendar_entry", "calendar_entry_created"),
        _write_result("create_task_item", "task_item_created"),
    ]:
        assert _names(middleware._prepare_request(_request([result]))) == TOOL_NAMES


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
    first_error = _write_result("create_calendar_entry", "calendar_entry_created", status="error")
    second_error = _write_result("create_calendar_entry", "calendar_entry_created", status="error")
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


def test_runtime_context_is_inserted_immediately_before_current_user_message() -> None:
    middleware = SchedulingToolBindingMiddleware(
        runtime_context="Current Beijing datetime: 2026-07-27T16:20"
    )
    request = _request(
        [
            HumanMessage(content="昨天的消息"),
            AIMessage(content="昨天的回复"),
            HumanMessage(content="明天上午去跳舞"),
            AIMessage(content=""),
            _search_result("search_calendar_entries"),
        ]
    )

    prepared = middleware._prepare_request(request)

    assert [type(message) for message in prepared.messages] == [
        HumanMessage,
        AIMessage,
        SystemMessage,
        HumanMessage,
        AIMessage,
        ToolMessage,
    ]
    assert prepared.messages[2].content == ("Current Beijing datetime: 2026-07-27T16:20")


def test_runtime_context_injection_is_idempotent() -> None:
    middleware = SchedulingToolBindingMiddleware(
        runtime_context="Current Beijing datetime: 2026-07-27T16:20"
    )
    prepared = middleware._prepare_request(_request([HumanMessage(content="明天上午去跳舞")]))

    prepared_again = middleware._prepare_request(prepared)

    assert sum(isinstance(message, SystemMessage) for message in prepared_again.messages) == 1


def test_successful_write_returns_to_model_for_remaining_dependent_work() -> None:
    async def run():
        middleware = SchedulingToolBindingMiddleware()
        request = _request(
            [
                HumanMessage(content="明天九点跳舞，跳完再唱歌，再完成买菜待办"),
                AIMessage(content=""),
                _write_result("create_calendar_entry", "calendar_entry_created"),
            ]
        )

        async def handler(prepared):
            assert _names(prepared) == TOOL_NAMES
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_calendar_entries",
                        "args": {"title_query": "跳舞"},
                        "id": "anchor-search",
                    }
                ],
            )

        return await middleware.awrap_model_call(request, handler)

    response = asyncio.run(run())
    assert response.tool_calls[0]["name"] == "search_calendar_entries"


def test_mixed_write_batch_still_allows_model_to_finish_or_continue() -> None:
    request = _request(
        [
            _write_result("create_calendar_entry", "calendar_entry_created"),
            _write_result("create_task_item", "task_item_created"),
        ]
    )
    expected = AIMessage(content="完成，还需要处理取消操作")
    assert (
        SchedulingToolBindingMiddleware().wrap_model_call(request, lambda prepared: expected)
        is expected
    )


def test_two_errors_in_one_batch_get_one_recovery_round() -> None:
    request = _request(
        [
            HumanMessage(content="安排两件事"),
            AIMessage(content=""),
            _write_result("create_calendar_entry", "error", status="error"),
            _write_result("create_task_item", "error", status="error"),
        ]
    )
    assert _names(SchedulingToolBindingMiddleware()._prepare_request(request)) == TOOL_NAMES


def test_successful_recovery_resets_failed_rounds_for_later_operations() -> None:
    request = _request(
        [
            HumanMessage(content="安排两件事"),
            AIMessage(content=""),
            _write_result("create_calendar_entry", "error", status="error"),
            AIMessage(content=""),
            _write_result("create_calendar_entry", "calendar_entry_created"),
            AIMessage(content=""),
            _write_result("create_task_item", "error", status="error"),
        ]
    )
    assert _names(SchedulingToolBindingMiddleware()._prepare_request(request)) == TOOL_NAMES


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
        artifact={"item": {"value": {"start_time": "2026-07-24T08:00:00+00:00"}}},
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
