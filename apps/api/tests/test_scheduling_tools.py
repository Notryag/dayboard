from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.tools import (
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    create_calendar_entry,
    create_task_item,
    list_calendar_entries,
    list_task_items,
)


async def test_create_and_list_calendar_entry(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    result = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="产品复盘",
            start_time=datetime(2026, 7, 10, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone="Asia/Shanghai",
            participants=["Alice"],
        ),
    )

    entries = await list_calendar_entries(db_session, tenant_context)

    assert result.type == "calendar_entry_created"
    assert result.requires_follow_up is False
    assert result.calendar_entry.title == "产品复盘"
    assert result.calendar_entry.tenant_id == tenant_context.tenant_id
    assert result.calendar_entry.owner_user_id == tenant_context.user_id
    assert entries == [result.calendar_entry]


async def test_create_and_list_task_item(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    result = await create_task_item(
        db_session,
        tenant_context,
        CreateTaskItemInput(
            title="整理周报",
            due_at=datetime(2026, 7, 10, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone="Asia/Shanghai",
        ),
    )

    tasks = await list_task_items(db_session, tenant_context)

    assert result.type == "task_item_created"
    assert result.requires_follow_up is False
    assert result.task_item.title == "整理周报"
    assert result.task_item.tenant_id == tenant_context.tenant_id
    assert result.task_item.owner_user_id == tenant_context.user_id
    assert tasks == [result.task_item]
