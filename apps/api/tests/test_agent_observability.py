from north import RuntimeEvent

from dayboard.agent.observability import project_runtime_event


def test_tool_start_projection_exposes_only_safe_product_fields() -> None:
    projected = project_runtime_event(
        RuntimeEvent(
            event_type="tool.started",
            category="tool",
            content={
                "title": "提交周报",
                "due_at": "2026-07-10T18:00:00+08:00",
                "password": "must-not-leak",
                "tenant_id": "must-not-leak",
            },
            metadata={"call_id": "call-1", "tool_name": "create_task_item"},
        )
    )

    assert projected is not None
    assert projected.event_type == "tool_call_started"
    assert projected.content == "正在创建任务“提交周报”，截止 2026-07-10T18:00:00+08:00"
    assert projected.metadata["inputs"] == {
        "title": "提交周报",
        "due_at": "2026-07-10T18:00:00+08:00",
    }
    assert "must-not-leak" not in str(projected)


def test_model_projection_does_not_persist_message_or_reasoning_content() -> None:
    projected = project_runtime_event(
        RuntimeEvent(
            event_type="model.completed",
            category="model",
            content={"reasoning_content": "private reasoning", "content": "raw answer"},
            metadata={
                "call_id": "model-1",
                "caller": "lead_agent",
                "latency_ms": 120,
                "usage": {"input_tokens": 10, "output_tokens": 5, "secret": "hidden"},
            },
        )
    )

    assert projected is not None
    assert projected.content == "已完成分析，正在执行下一步"
    assert projected.metadata["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert "private reasoning" not in str(projected)
    assert "raw answer" not in str(projected)
    assert "hidden" not in str(projected)


def test_cancel_search_and_tool_have_product_specific_progress() -> None:
    search = project_runtime_event(
        RuntimeEvent(
            event_type="tool.started",
            category="tool",
            content={
                "start_time": "2026-07-11T00:00:00+08:00",
                "end_time": "2026-07-12T00:00:00+08:00",
                "purpose": "cancel",
            },
            metadata={"call_id": "call-2", "tool_name": "search_calendar_entries"},
        )
    )
    cancel = project_runtime_event(
        RuntimeEvent(
            event_type="tool.started",
            category="tool",
            content={
                "calendar_entry_id": "00000000-0000-0000-0000-000000000001",
                "expected_updated_at": "2026-07-10T12:00:00+00:00",
                "secret": "must-not-leak",
            },
            metadata={"call_id": "call-3", "tool_name": "cancel_calendar_entry"},
        )
    )

    assert search is not None
    assert search.content.startswith("正在查找要取消的日程")
    assert cancel is not None
    assert cancel.content == "正在取消日程"
    assert "must-not-leak" not in str(cancel)
