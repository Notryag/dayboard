from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent import build_scheduling_tools
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
    search_tasks = next(tool for tool in tools if tool.name == "search_task_items")
    update_task = next(tool for tool in tools if tool.name == "update_task_item")

    schema = create_entry.args_schema.model_json_schema()
    fields = set(schema["properties"])

    assert "title" in fields
    assert "start_time" in fields
    assert "timezone" not in fields
    assert "tenant_id" not in fields
    assert "user_id" not in fields
    assert "owner_user_id" not in fields
    assert "created_by_run_id" not in fields
    assert set(check_conflicts.args_schema.model_json_schema()["properties"]) == {
        "start_time",
        "end_time",
    }
    assert set(search_entries.args_schema.model_json_schema()["properties"]) == {
        "start_time",
        "end_time",
        "title_query",
        "purpose",
    }
    assert set(reschedule_entry.args_schema.model_json_schema()["properties"]) == {
        "calendar_entry_id",
        "new_date",
        "new_start_time",
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
    assert set(update_task.args_schema.model_json_schema()["properties"]) == {
        "task_item_id",
        "expected_updated_at",
        "new_title",
        "new_due_at",
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
        "start_time": "2026-07-10T10:00:00+08:00",
        "participants": ["Alice"],
    }
    task_input = {
        "title": "整理会议纪要",
        "due_at": "2026-07-10T18:00:00+08:00",
    }
    entry_result = await create_entry.ainvoke(entry_input)
    second_entry_result = await create_entry.ainvoke(
        {"title": "客户会议", "start_time": "2026-07-10T11:00:00+08:00"}
    )
    repeated_entry_result = await create_entry.ainvoke(entry_input)
    task_result = await create_task.ainvoke(task_input)
    second_task_result = await create_task.ainvoke(
        {"title": "回复邮件", "due_at": "2026-07-11T18:00:00+08:00"}
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
        "updated_at",
    }
    assert "tenant_id" not in str(entry_result)
    assert "created_by_run_id" not in str(entry_result)
    assert set(task_result["task_item"]) == {
        "id",
        "title",
        "due_at",
        "timezone",
        "status",
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
    assert tasks[0].tenant_id == tenant_context.tenant_id
    assert tasks[0].owner_user_id == tenant_context.user_id
    assert tasks[0].created_by_run_id == run_id
    assert tasks[0].timezone == tenant_context.timezone
    assert progress_events == []


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
