from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from north import RuntimeEvent

from dayboard.domain.runs import AgentRunEventCategory


@dataclass(frozen=True, slots=True)
class ProjectedRuntimeEvent:
    event_type: str
    category: AgentRunEventCategory
    content: str
    metadata: dict[str, Any]


def project_runtime_event(event: RuntimeEvent) -> ProjectedRuntimeEvent | None:
    if event.event_type == "model.started":
        return ProjectedRuntimeEvent(
            "agent_model_started",
            AgentRunEventCategory.model,
            "正在理解你的安排",
            _model_metadata(event.metadata),
        )
    if event.event_type == "model.completed":
        return ProjectedRuntimeEvent(
            "agent_model_completed",
            AgentRunEventCategory.model,
            "已完成分析，正在执行下一步",
            _model_metadata(event.metadata),
        )
    if event.event_type == "model.error":
        return ProjectedRuntimeEvent(
            "agent_model_error",
            AgentRunEventCategory.error,
            "分析过程发生错误",
            _error_metadata(event.metadata),
        )
    if event.event_type == "tool.started":
        tool_name = _tool_name(event.metadata)
        safe_inputs = _safe_tool_inputs(tool_name, event.content)
        return ProjectedRuntimeEvent(
            "tool_call_started",
            AgentRunEventCategory.tool,
            _tool_started_text(tool_name, safe_inputs),
            {
                "call_id": event.metadata.get("call_id"),
                "tool_name": tool_name,
                "inputs": safe_inputs,
            },
        )
    if event.event_type == "tool.completed":
        tool_name = _tool_name(event.metadata)
        return ProjectedRuntimeEvent(
            "tool_call_completed",
            AgentRunEventCategory.tool,
            f"{_tool_label(tool_name)}完成",
            _tool_terminal_metadata(event.metadata),
        )
    if event.event_type == "tool.error":
        tool_name = _tool_name(event.metadata)
        return ProjectedRuntimeEvent(
            "tool_call_error",
            AgentRunEventCategory.error,
            f"{_tool_label(tool_name)}失败",
            {**_tool_terminal_metadata(event.metadata), **_error_metadata(event.metadata)},
        )
    return None


def _model_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    usage = metadata.get("usage")
    safe_usage = {}
    if isinstance(usage, dict):
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and value >= 0:
                safe_usage[key] = value
    return {
        "call_id": metadata.get("call_id"),
        "call_index": metadata.get("call_index"),
        "caller": metadata.get("caller"),
        "latency_ms": metadata.get("latency_ms"),
        "usage": safe_usage,
    }


def _error_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {"error_type": metadata.get("error_type")}


def _tool_name(metadata: dict[str, Any]) -> str:
    value = metadata.get("tool_name")
    return value if isinstance(value, str) and value else "unknown"


def _safe_tool_inputs(tool_name: str, content: Any) -> dict[str, Any]:
    if not isinstance(content, dict):
        return {}
    allowed_fields = {
        "create_calendar_entry": ("title", "start_time", "end_time"),
        "check_calendar_conflicts": ("start_time", "end_time"),
        "create_task_item": ("title", "due_at", "status"),
    }.get(tool_name, ())
    return {key: content[key] for key in allowed_fields if key in content}


def _tool_started_text(tool_name: str, inputs: dict[str, Any]) -> str:
    title = inputs.get("title")
    if tool_name == "create_calendar_entry":
        return (
            "正在创建日程"
            + (f"“{title}”" if title else "")
            + _time_suffix(inputs.get("start_time"), inputs.get("end_time"))
        )
    if tool_name == "create_task_item":
        due_at = inputs.get("due_at")
        return (
            "正在创建任务"
            + (f"“{title}”" if title else "")
            + (f"，截止 {due_at}" if due_at else "")
        )
    if tool_name == "check_calendar_conflicts":
        return "正在查询日程冲突" + _time_suffix(
            inputs.get("start_time"), inputs.get("end_time")
        )
    return {
        "list_calendar_entries": "正在查询日程",
        "list_task_items": "正在查询任务",
        "ask_clarification": "正在确认缺少的信息",
    }.get(tool_name, "正在执行操作")


def _tool_label(tool_name: str) -> str:
    return {
        "create_calendar_entry": "创建日程",
        "check_calendar_conflicts": "查询日程冲突",
        "list_calendar_entries": "查询日程",
        "create_task_item": "创建任务",
        "list_task_items": "查询任务",
        "ask_clarification": "信息确认",
    }.get(tool_name, "操作")


def _tool_terminal_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_id": metadata.get("call_id"),
        "tool_name": _tool_name(metadata),
        "latency_ms": metadata.get("latency_ms"),
    }


def _time_suffix(start_time: Any, end_time: Any) -> str:
    if not start_time:
        return ""
    return f"（{start_time}" + (f" 至 {end_time}" if end_time else "") + "）"
