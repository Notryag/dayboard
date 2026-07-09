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

    schema = create_entry.args_schema.model_json_schema()
    fields = set(schema["properties"])

    assert "title" in fields
    assert "start_time" in fields
    assert "tenant_id" not in fields
    assert "user_id" not in fields
    assert "owner_user_id" not in fields
    assert "created_by_run_id" not in fields


async def test_agent_scheduling_tools_inject_run_and_tenant_context(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run_id = uuid4()
    tools = build_scheduling_tools(session=db_session, context=tenant_context, run_id=run_id)
    create_entry = next(tool for tool in tools if tool.name == "create_calendar_entry")
    create_task = next(tool for tool in tools if tool.name == "create_task_item")

    entry_result = await create_entry.ainvoke(
        {
            "title": "产品复盘",
            "start_time": "2026-07-10T10:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "participants": ["Alice"],
        }
    )
    task_result = await create_task.ainvoke(
        {
            "title": "整理会议纪要",
            "due_at": "2026-07-10T18:00:00+08:00",
            "timezone": "Asia/Shanghai",
        }
    )

    assert entry_result["type"] == "calendar_entry_created"
    assert task_result["type"] == "task_item_created"

    entries = await list_calendar_entries(db_session, tenant_context)
    tasks = await list_task_items(db_session, tenant_context)

    assert entries[0].tenant_id == tenant_context.tenant_id
    assert entries[0].owner_user_id == tenant_context.user_id
    assert entries[0].created_by_run_id == run_id
    assert tasks[0].tenant_id == tenant_context.tenant_id
    assert tasks[0].owner_user_id == tenant_context.user_id
    assert tasks[0].created_by_run_id == run_id
