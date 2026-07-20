import asyncio
import json

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from dayboard.agent.middleware import TerminalWriteToolPruningMiddleware


def _request(messages, tools=None) -> ModelRequest:
    return ModelRequest(model=object(), messages=messages, tools=tools or ["all-tools"])


def _tool_result(name: str, result_type: str, *, status: str = "success") -> ToolMessage:
    return ToolMessage(
        content=json.dumps({"type": result_type}),
        tool_call_id=f"call-{name}",
        name=name,
        status=status,
    )


def test_prunes_tools_after_successful_terminal_writes() -> None:
    middleware = TerminalWriteToolPruningMiddleware()
    request = _request(
        [
            HumanMessage(content="安排两件事"),
            AIMessage(content=""),
            _tool_result("create_calendar_entry", "calendar_entry_created"),
            _tool_result("create_task_item", "task_item_created"),
        ]
    )
    captured = {}

    middleware.wrap_model_call(
        request,
        lambda prepared: captured.setdefault("tools", prepared.tools),
    )

    assert captured["tools"] == []


def test_keeps_tools_after_search_or_error_results() -> None:
    middleware = TerminalWriteToolPruningMiddleware()
    search = _request(
        [_tool_result("search_calendar_entries", "calendar_entries_found")]
    )
    error = _request(
        [
            _tool_result(
                "create_calendar_entry",
                "calendar_entry_created",
                status="error",
            )
        ]
    )

    assert middleware._prepare_request(search).tools == ["all-tools"]
    assert middleware._prepare_request(error).tools == ["all-tools"]


def test_keeps_tools_on_the_next_user_turn() -> None:
    middleware = TerminalWriteToolPruningMiddleware()
    request = _request(
        [
            _tool_result("create_task_item", "task_item_created"),
            AIMessage(content="已添加"),
            HumanMessage(content="再加一个"),
        ]
    )

    assert middleware._prepare_request(request).tools == ["all-tools"]


def test_async_wrapper_uses_the_same_terminal_policy() -> None:
    async def run() -> list:
        middleware = TerminalWriteToolPruningMiddleware()
        request = _request([_tool_result("update_task_item", "task_item_updated")])

        async def handler(prepared):
            return prepared.tools

        return await middleware.awrap_model_call(request, handler)

    assert asyncio.run(run()) == []
