from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from north import RuntimeEvent

from agent_platform.core import AgentRunEventCategory


@dataclass(frozen=True, slots=True)
class ProjectedRuntimeEvent:
    event_type: str
    category: AgentRunEventCategory
    content: str
    metadata: dict[str, Any]


def project_runtime_event(event: RuntimeEvent) -> ProjectedRuntimeEvent | None:
    if event.event_type == "model.started":
        call_index = event.metadata.get("call_index")
        return ProjectedRuntimeEvent(
            "agent_model_started",
            AgentRunEventCategory.model,
            "正在理解你的安排" if call_index in (None, 1) else "正在整理处理结果",
            _model_metadata(event.metadata),
        )
    if event.event_type == "model.completed":
        call_index = event.metadata.get("call_index")
        return ProjectedRuntimeEvent(
            "agent_model_completed",
            AgentRunEventCategory.model,
            "已完成分析，正在执行下一步" if call_index in (None, 1) else "处理结果已整理完成",
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
        error_type = event.metadata.get("error_type")
        return ProjectedRuntimeEvent(
            "tool_call_error",
            AgentRunEventCategory.error,
            (
                f"{_tool_label(tool_name)}参数需要调整，正在重试"
                if error_type == "ValidationError"
                else f"{_tool_label(tool_name)}失败"
            ),
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
        "create_calendar_entry": (
            "title",
            "local_start",
            "local_end",
            "anchor_entry_id",
            "expected_anchor_row_version",
        ),
        "search_calendar_entries": ("local_start", "local_end", "title_query"),
        "reschedule_calendar_entry": (
            "calendar_entry_id",
            "new_date",
            "new_local_start",
            "new_local_end",
            "new_duration_minutes",
            "expected_row_version",
        ),
        "cancel_calendar_entry": (
            "calendar_entry_id",
            "expected_row_version",
            "reason",
        ),
        "create_task_item": ("title",),
        "search_task_items": ("title_query", "status"),
        "update_task_item": (
            "new_title",
            "new_status",
            "expected_row_version",
        ),
    }.get(tool_name, ())
    return {key: content[key] for key in allowed_fields if key in content}


def _tool_started_text(tool_name: str, inputs: dict[str, Any]) -> str:
    title = inputs.get("title")
    if tool_name == "create_calendar_entry":
        return (
            "正在创建日程"
            + (f"“{title}”" if title else "")
            + _time_suffix(inputs.get("local_start"), inputs.get("local_end"))
        )
    if tool_name == "create_task_item":
        return "正在创建任务" + (f"“{title}”" if title else "")
    if tool_name == "search_calendar_entries":
        return "正在查找日程" + _time_suffix(
            inputs.get("local_start"), inputs.get("local_end")
        )
    if tool_name == "reschedule_calendar_entry":
        start = inputs.get("new_local_start") or inputs.get("new_date")
        end = inputs.get("new_local_end")
        if start and end:
            return f"正在修改日程时间为 {start} 至 {end}"
        if end:
            return f"正在修改日程结束时间为 {end}"
        return f"正在修改日程时间为 {start}"
    if tool_name == "cancel_calendar_entry":
        return "正在取消日程"
    if tool_name == "search_task_items":
        return "正在查找任务"
    if tool_name == "update_task_item":
        status = inputs.get("new_status")
        if status == "completed":
            return "正在完成任务"
        if status == "cancelled":
            return "正在取消任务"
        return "正在修改任务"
    return {
        "ask_clarification": "正在确认缺少的信息",
    }.get(tool_name, "正在执行操作")


def _tool_label(tool_name: str) -> str:
    return {
        "create_calendar_entry": "创建日程",
        "search_calendar_entries": "查找日程",
        "reschedule_calendar_entry": "修改日程",
        "cancel_calendar_entry": "取消日程",
        "create_task_item": "创建任务",
        "search_task_items": "查找任务",
        "update_task_item": "修改任务",
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
