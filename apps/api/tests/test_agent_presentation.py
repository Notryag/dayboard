from north import RuntimeStreamEvent

from dayboard.agent.presentation import project_runtime_stream_event


def test_projects_structured_tool_message_to_schedule_part() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            data=[
                {
                    "type": "tool",
                    "name": "create_task_item",
                    "tool_call_id": "call-1",
                    "content": (
                        '{"type":"task_item_created","task_item":{'
                        '"id":"task-1","title":"提交周报","due_at":null,'
                        '"timezone":"Asia/Shanghai","reminder":null,"status":"open",'
                        '"created_by_run_id":"run-1","created_at":"2026-07-20T10:00:00Z",'
                        '"updated_at":"2026-07-20T10:00:00Z",'
                        '"tenant_id":"must-not-leak"}}'
                    ),
                },
                {"langgraph_node": "tools"},
            ],
        )
    )

    assert projected is not None
    assert projected.event_type == "schedule_item_result"
    assert projected.data["tool_call_id"] == "call-1"
    assert projected.data["item"]["kind"] == "task"
    assert projected.data["item"]["value"]["title"] == "提交周报"
    assert "tenant_id" not in projected.data["item"]["value"]


def test_projects_ai_message_chunk_to_text_delta() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            data=[{"type": "AIMessageChunk", "id": "message-1", "content": "已创建"}, {}],
        )
    )

    assert projected is not None
    assert projected.event_type == "assistant_text_delta"
    assert projected.data == {"message_id": "message-1", "delta": "已创建"}


def test_rejects_unrecognized_tool_output() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            data=[
                {
                    "type": "tool",
                    "name": "search_task_items",
                    "tool_call_id": "call-1",
                    "content": '{"type":"search_results","items":[]}',
                },
                {},
            ],
        )
    )

    assert projected is None


def test_rejects_tool_messages_from_untrusted_subgraph_namespace() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            namespace=("untrusted-subgraph",),
            data=[
                {
                    "type": "tool",
                    "name": "create_task_item",
                    "tool_call_id": "call-1",
                    "content": {
                        "type": "task_item_created",
                        "task_item": {
                            "id": "task-1",
                            "title": "不应显示",
                            "timezone": "Asia/Shanghai",
                            "status": "open",
                            "updated_at": "2026-07-20T10:00:00Z",
                        },
                    },
                },
                {},
            ],
        )
    )

    assert projected is None
