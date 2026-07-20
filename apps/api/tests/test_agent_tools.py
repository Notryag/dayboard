from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent import build_scheduling_tools
from dayboard.agent.tools import AgentCreateCalendarEntryInput
from dayboard.context import TenantContext
from dayboard.tools import list_calendar_entries, list_task_items


async def test_agent_scheduling_tool_schema_hides_trusted_context(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    tools = build_scheduling_tools(session=db_session, context=tenant_context, run_id=uuid4())
    create_entry = next(tool for tool in tools if tool.name == "create_calendar_entry")
    check_conflicts = next(tool for tool in tools if tool.name == "check_calendar_conflicts")
    search_entries = next(tool for tool in tools if tool.name == "search_calendar_entries")
    reschedule_entry = next(tool for tool in tools if tool.name == "reschedule_calendar_entry")
    cancel_entry = next(tool for tool in tools if tool.name == "cancel_calendar_entry")
    create_task = next(tool for tool in tools if tool.name == "create_task_item")
    search_tasks = next(tool for tool in tools if tool.name == "search_task_items")
    update_task = next(tool for tool in tools if tool.name == "update_task_item")

    schema = create_entry.args_schema.model_json_schema()
    fields = set(schema["properties"])

    assert "title" in fields
    assert "local_start" in fields
    assert "local_end" in fields
    assert "start_time" not in fields
    assert "timezone" not in fields
    assert "tenant_id" not in fields
    assert "user_id" not in fields
    assert "owner_user_id" not in fields
    assert "created_by_run_id" not in fields
    assert "Defaults to PT0M" in schema["properties"]["reminder"]["description"]
    assert set(check_conflicts.args_schema.model_json_schema()["properties"]) == {
        "local_start",
        "local_end",
    }
    assert set(search_entries.args_schema.model_json_schema()["properties"]) == {
        "start_date",
        "end_date",
        "title_query",
        "purpose",
    }
    assert set(reschedule_entry.args_schema.model_json_schema()["properties"]) == {
        "calendar_entry_id",
        "new_date",
        "new_local_start",
        "new_local_end",
        "expected_updated_at",
    }
    assert set(cancel_entry.args_schema.model_json_schema()["properties"]) == {
        "calendar_entry_id",
        "expected_updated_at",
        "reason",
    }
    assert set(search_tasks.args_schema.model_json_schema()["properties"]) == {
        "title_query",
        "status",
        "purpose",
    }
    assert set(create_task.args_schema.model_json_schema()["properties"]) == {
        "title",
        "due_local",
        "reminder",
        "status",
    }
    assert set(update_task.args_schema.model_json_schema()["properties"]) == {
        "task_item_id",
        "expected_updated_at",
        "new_title",
        "new_due_local",
        "new_status",
    }


async def test_agent_scheduling_tools_inject_run_and_tenant_context(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_id = uuid4()
    progress_events: list[tuple[str, str, dict]] = []

    async def record_progress(event_type: str, content: str, metadata: dict) -> None:
        progress_events.append((event_type, content, metadata))

    tools = build_scheduling_tools(
        session=db_session,
        context=tenant_context,
        run_id=run_id,
        progress=record_progress,
    )
    create_entry = next(tool for tool in tools if tool.name == "create_calendar_entry")
    create_task = next(tool for tool in tools if tool.name == "create_task_item")

    entry_input = {
        "title": "产品复盘",
        "local_start": "2026-07-10T10:00:00",
        "participants": ["Alice"],
    }
    task_input = {
        "title": "整理会议纪要",
        "due_local": "2026-07-10T18:00:00",
    }
    entry_result = await create_entry.ainvoke(entry_input)
    second_entry_result = await create_entry.ainvoke(
        {
            "title": "客户会议",
            "local_start": "2026-07-10T11:00:00",
            "reminder": None,
        }
    )
    repeated_entry_result = await create_entry.ainvoke(entry_input)
    task_result = await create_task.ainvoke(task_input)
    second_task_result = await create_task.ainvoke(
        {"title": "回复邮件", "due_local": "2026-07-11T18:00:00"}
    )
    repeated_task_result = await create_task.ainvoke(task_input)

    assert entry_result["type"] == "calendar_entry_created"
    assert task_result["type"] == "task_item_created"
    assert repeated_entry_result["calendar_entry_id"] == entry_result["calendar_entry_id"]
    assert repeated_task_result["task_item_id"] == task_result["task_item_id"]
    assert second_entry_result["calendar_entry_id"] != entry_result["calendar_entry_id"]
    assert second_task_result["task_item_id"] != task_result["task_item_id"]
    assert set(entry_result["calendar_entry"]) == {
        "id",
        "title",
        "start_time",
        "end_time",
        "timezone",
        "participants",
        "reminder",
        "status",
        "created_by_run_id",
        "created_at",
        "updated_at",
    }
    assert "tenant_id" not in str(entry_result)
    assert set(task_result["task_item"]) == {
        "id",
        "title",
        "due_at",
        "timezone",
        "reminder",
        "status",
        "created_by_run_id",
        "created_at",
        "updated_at",
    }

    entries = await list_calendar_entries(db_session, tenant_context)
    tasks = await list_task_items(db_session, tenant_context)

    assert len(entries) == 2
    assert len(tasks) == 2
    assert entries[0].tenant_id == tenant_context.tenant_id
    assert entries[0].owner_user_id == tenant_context.user_id
    assert entries[0].created_by_run_id == run_id
    assert entries[0].timezone == tenant_context.timezone
    assert entries[0].start_time.astimezone(ZoneInfo("Asia/Shanghai")) == datetime(
        2026, 7, 10, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert entries[0].reminder is not None
    assert entries[0].reminder.offset == "PT0M"
    assert entries[0].reminder.anchor == "start_time"
    assert entries[1].reminder is None
    assert tasks[0].tenant_id == tenant_context.tenant_id
    assert tasks[0].owner_user_id == tenant_context.user_id
    assert tasks[0].created_by_run_id == run_id
    assert tasks[0].timezone == tenant_context.timezone
    assert datetime.fromisoformat(task_result["task_item"]["due_at"]).astimezone(
        ZoneInfo("Asia/Shanghai")
    ).hour == 18
    assert progress_events == []


def test_agent_local_datetime_inputs_reject_timezone_offsets() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        AgentCreateCalendarEntryInput.model_validate(
            {
                "title": "产品复盘",
                "local_start": "2026-07-10T10:00:00+08:00",
            }
        )


async def test_agent_search_and_reschedule_resolve_local_beijing_time(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    tools = build_scheduling_tools(
        session=db_session,
        context=tenant_context,
        run_id=uuid4(),
    )
    check_conflicts = next(tool for tool in tools if tool.name == "check_calendar_conflicts")
    create_entry = next(tool for tool in tools if tool.name == "create_calendar_entry")
    search_entries = next(tool for tool in tools if tool.name == "search_calendar_entries")
    reschedule_entry = next(tool for tool in tools if tool.name == "reschedule_calendar_entry")

    created = await create_entry.ainvoke(
        {
            "title": "吃饭",
            "local_start": "2026-07-14T12:00:00",
            "local_end": "2026-07-14T13:00:00",
        }
    )
    conflict = await check_conflicts.ainvoke(
        {
            "local_start": "2026-07-14T12:30:00",
            "local_end": "2026-07-14T13:30:00",
        }
    )
    matches = await search_entries.ainvoke(
        {
            "start_date": "2026-07-14",
            "end_date": "2026-07-14",
            "title_query": "吃饭",
            "purpose": "reschedule",
        }
    )
    updated = await reschedule_entry.ainvoke(
        {
            "calendar_entry_id": created["calendar_entry_id"],
            "new_local_end": "2026-07-14T17:00:00",
            "expected_updated_at": matches[0]["updated_at"],
        }
    )

    assert len(conflict["conflicts"]) == 1
    assert len(matches) == 1
    assert datetime.fromisoformat(updated["calendar_entry"]["start_time"]).astimezone(
        ZoneInfo("Asia/Shanghai")
    ).hour == 12
    assert datetime.fromisoformat(updated["calendar_entry"]["end_time"]).astimezone(
        ZoneInfo("Asia/Shanghai")
    ).hour == 17


async def test_agent_task_due_times_resolve_from_local_beijing_time(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    tools = build_scheduling_tools(
        session=db_session,
        context=tenant_context,
        run_id=uuid4(),
    )
    create_task = next(tool for tool in tools if tool.name == "create_task_item")
    search_tasks = next(tool for tool in tools if tool.name == "search_task_items")
    update_task = next(tool for tool in tools if tool.name == "update_task_item")

    created = await create_task.ainvoke(
        {"title": "交作业", "due_local": "2026-07-14T18:00:00"}
    )
    matches = await search_tasks.ainvoke(
        {"title_query": "交作业", "status": "open", "purpose": "update"}
    )
    updated = await update_task.ainvoke(
        {
            "task_item_id": created["task_item_id"],
            "expected_updated_at": matches[0]["updated_at"],
            "new_due_local": "2026-07-14T20:00:00",
        }
    )

    assert len(matches) == 1
    assert datetime.fromisoformat(updated["task_item"]["due_at"]).astimezone(
        ZoneInfo("Asia/Shanghai")
    ).hour == 20


async def test_parallel_agent_tool_calls_are_serialized_on_shared_session(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    tools = build_scheduling_tools(
        session=db_session,
        context=tenant_context,
        run_id=uuid4(),
    )
    create_task = next(tool for tool in tools if tool.name == "create_task_item")

    first, second = await asyncio.gather(
        create_task.ainvoke({"title": "并行任务一"}),
        create_task.ainvoke({"title": "并行任务二"}),
    )

    assert first["task_item_id"] != second["task_item_id"]
    tasks = await list_task_items(db_session, tenant_context)
    assert {task.title for task in tasks} == {"并行任务一", "并行任务二"}
