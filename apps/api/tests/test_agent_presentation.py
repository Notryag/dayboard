from north import RuntimeStreamEvent

from dayboard.agent.presentation import project_runtime_stream_event


TASK_ID = "11111111-1111-4111-8111-111111111111"
CALENDAR_ID_1 = "22222222-2222-4222-8222-222222222222"
CALENDAR_ID_2 = "33333333-3333-4333-8333-333333333333"


def _task_value(*, title: str = "提交周报") -> dict:
    return {
        "id": TASK_ID,
        "title": title,
        "due_at": None,
        "timezone": "Asia/Shanghai",
        "reminder": None,
        "status": "open",
        "created_by_run_id": None,
        "created_at": "2026-07-20T10:00:00Z",
        "updated_at": "2026-07-20T10:00:00Z",
        "tenant_id": "must-not-leak",
    }


def _calendar_value(
    *,
    entry_id: str,
    title: str,
    timing_kind: str,
    scheduled_date: str | None,
    start_time: str | None,
    end_time: str | None,
) -> dict:
    return {
        "id": entry_id,
        "title": title,
        "timing_kind": timing_kind,
        "scheduled_date": scheduled_date,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": "Asia/Shanghai",
        "participants": [],
        "reminder": None,
        "status": "scheduled",
        "created_by_run_id": None,
        "created_at": "2026-07-22T01:00:00Z",
        "updated_at": "2026-07-22T01:00:00Z",
    }


def test_projects_structured_tool_message_artifact_to_schedule_part() -> None:
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
                        f'"id":"{TASK_ID}","title":"提交周报",'
                        '"status":"open","updated_at":"2026-07-20T10:00:00Z"}}'
                    ),
                    "artifact": {
                        "type": "schedule_item_result",
                        "operation": "task_item_created",
                        "item": {"kind": "task", "value": _task_value()},
                    },
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


def test_rejects_tool_message_without_presentation_artifact() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            data=[
                {
                    "type": "tool",
                    "name": "create_task_item",
                    "tool_call_id": "call-1",
                    "content": '{"type":"task_item_created","task_item":{}}',
                },
                {},
            ],
        )
    )

    assert projected is None


def test_projects_calendar_search_artifact_to_schedule_parts() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            data=[
                {
                    "type": "tool",
                    "name": "search_calendar_entries",
                    "tool_call_id": "call-search",
                    "content": "[]",
                    "artifact": {
                        "type": "schedule_items_result",
                        "operation": "calendar_entry_found",
                        "items": [
                            {
                                "kind": "calendar",
                                "value": _calendar_value(
                                    entry_id=CALENDAR_ID_1,
                                    title="明日晨会",
                                    timing_kind="timed",
                                    scheduled_date=None,
                                    start_time="2026-07-23T09:00:00+08:00",
                                    end_time="2026-07-23T10:00:00+08:00",
                                ),
                            },
                            {
                                "kind": "calendar",
                                "value": _calendar_value(
                                    entry_id=CALENDAR_ID_2,
                                    title="提交材料",
                                    timing_kind="anytime",
                                    scheduled_date="2026-07-23",
                                    start_time=None,
                                    end_time=None,
                                ),
                            },
                        ],
                    },
                },
                {},
            ],
        )
    )

    assert projected is not None
    assert projected.event_type == "schedule_items_result"
    assert [part["item"]["value"]["title"] for part in projected.data["parts"]] == [
        "明日晨会",
        "提交材料",
    ]
    assert all(part["operation"] == "calendar_entry_found" for part in projected.data["parts"])


def test_rejects_malformed_presentation_artifact() -> None:
    projected = project_runtime_stream_event(
        RuntimeStreamEvent(
            mode="messages",
            data=[
                {
                    "type": "tool",
                    "name": "create_task_item",
                    "tool_call_id": "call-1",
                    "content": "{}",
                    "artifact": {
                        "type": "schedule_item_result",
                        "operation": "task_item_created",
                        "item": {"kind": "task", "value": {"id": "invalid"}},
                    },
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
                    "content": "{}",
                    "artifact": {
                        "type": "schedule_item_result",
                        "operation": "task_item_created",
                        "item": {"kind": "task", "value": _task_value(title="不应显示")},
                    },
                },
                {},
            ],
        )
    )

    assert projected is None
