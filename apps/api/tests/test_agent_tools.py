from __future__ import annotations

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

    entry_result = await create_entry.ainvoke(
        {
            "title": "产品复盘",
            "start_time": "2026-07-10T10:00:00+08:00",
            "participants": ["Alice"],
        }
    )
    task_result = await create_task.ainvoke(
        {
            "title": "整理会议纪要",
            "due_at": "2026-07-10T18:00:00+08:00",
        }
    )
    repeated_entry_result = await create_entry.ainvoke(
        {
            "title": "不应重复创建",
            "start_time": "2026-07-10T11:00:00+08:00",
        }
    )
    repeated_task_result = await create_task.ainvoke(
        {
            "title": "不应重复创建的任务",
            "due_at": "2026-07-11T18:00:00+08:00",
        }
    )

    assert entry_result["type"] == "calendar_entry_created"
    assert task_result["type"] == "task_item_created"
    assert repeated_entry_result["calendar_entry_id"] == entry_result["calendar_entry_id"]
    assert repeated_task_result["task_item_id"] == task_result["task_item_id"]

    entries = await list_calendar_entries(db_session, tenant_context)
    tasks = await list_task_items(db_session, tenant_context)

    assert entries[0].tenant_id == tenant_context.tenant_id
    assert entries[0].owner_user_id == tenant_context.user_id
    assert entries[0].created_by_run_id == run_id
    assert entries[0].timezone == tenant_context.timezone
    assert tasks[0].tenant_id == tenant_context.tenant_id
    assert tasks[0].owner_user_id == tenant_context.user_id
    assert tasks[0].created_by_run_id == run_id
    assert tasks[0].timezone == tenant_context.timezone
    assert [event[0] for event in progress_events] == [
        "conflict_check_started",
        "conflict_check_completed",
        "conflict_check_started",
        "conflict_check_completed",
    ]
