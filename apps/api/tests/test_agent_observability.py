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
