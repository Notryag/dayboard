from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.tools import (
    CancelCalendarEntryInput,
    CalendarEntryChangedError,
    CreateCalendarEntryInput,
    CreateTaskItemInput,
    RescheduleCalendarEntryInput,
    SearchCalendarEntriesInput,
    create_calendar_entry,
    cancel_calendar_entry,
    create_task_item,
    check_calendar_conflicts,
    list_calendar_entries,
    list_task_items,
    reschedule_calendar_entry,
    search_calendar_entries,
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
    assert result.calendar_entry.end_time == datetime(
        2026, 7, 10, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    assert entries == [result.calendar_entry]


async def test_calendar_conflict_detection_warns_but_creates_overlapping_entry(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    first = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="晨会",
            start_time=datetime(2026, 7, 11, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone="Asia/Shanghai",
        ),
    )

    conflict = await check_calendar_conflicts(
        db_session,
        tenant_context,
        start_time=datetime(2026, 7, 11, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    created_with_warning = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="产品会",
            start_time=datetime(2026, 7, 11, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone="Asia/Shanghai",
        ),
    )
    entries = await list_calendar_entries(db_session, tenant_context)

    assert first.type == "calendar_entry_created"
    assert conflict.type == "calendar_conflict"
    assert conflict.requires_follow_up is True
    assert [entry.title for entry in conflict.conflicts] == ["晨会"]
    assert created_with_warning.type == "calendar_entry_created"
    assert [entry.title for entry in created_with_warning.conflicts] == ["晨会"]
    assert created_with_warning.requires_follow_up is False
    assert [entry.title for entry in entries] == ["晨会", "产品会"]


async def test_calendar_conflict_detection_allows_adjacent_entries(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="晨会",
            start_time=datetime(2026, 7, 11, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone="Asia/Shanghai",
        ),
    )

    adjacent = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="产品会",
            start_time=datetime(2026, 7, 11, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            timezone="Asia/Shanghai",
        ),
    )

    assert adjacent.type == "calendar_entry_created"


def test_calendar_input_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        CreateCalendarEntryInput(
            title="无时区会议",
            start_time=datetime(2026, 7, 11, 8, 0),
            timezone="Asia/Shanghai",
        )


async def test_calendar_creation_rejects_end_before_start(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    with pytest.raises(ValidationError, match="end_time must be after start_time"):
        await create_calendar_entry(
            db_session,
            tenant_context,
            CreateCalendarEntryInput(
                title="反向会议",
                start_time=datetime(2026, 7, 11, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                end_time=datetime(2026, 7, 11, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
                timezone="Asia/Shanghai",
            ),
        )


async def test_conflicts_compare_absolute_instants_across_offsets(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="上海会议",
            start_time="2026-07-11T08:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )

    result = await check_calendar_conflicts(
        db_session,
        tenant_context,
        start_time=datetime.fromisoformat("2026-07-11T00:30:00+00:00"),
        end_time=datetime.fromisoformat("2026-07-11T01:00:00+00:00"),
    )

    assert [entry.title for entry in result.conflicts] == ["上海会议"]


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


async def test_search_and_reschedule_calendar_entry_preserves_event_details(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    created = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="产品会议",
            start_time="2026-07-11T08:00:00+08:00",
            end_time="2026-07-11T09:30:00+08:00",
            timezone="Asia/Shanghai",
            participants=["Alice"],
        ),
    )
    matches = await search_calendar_entries(
        db_session,
        tenant_context,
        SearchCalendarEntriesInput(
            start_time="2026-07-11T00:00:00+08:00",
            end_time="2026-07-12T00:00:00+08:00",
            title_query="会议",
        ),
    )
    update_run_id = uuid4()
    moved = await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=matches[0].id,
            new_date="2026-07-12",
            expected_updated_at=matches[0].updated_at,
        ),
        updated_by_run_id=update_run_id,
    )
    repeated = await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=matches[0].id,
            new_start_time="2026-07-13T08:00:00+08:00",
            expected_updated_at=matches[0].updated_at,
        ),
        updated_by_run_id=update_run_id,
    )

    assert [entry.id for entry in matches] == [created.calendar_entry_id]
    assert moved.previous_start_time.isoformat() == "2026-07-11T00:00:00+00:00"
    assert moved.calendar_entry.start_time.isoformat() == "2026-07-12T00:00:00+00:00"
    assert moved.calendar_entry.end_time is not None
    assert moved.calendar_entry.end_time - moved.calendar_entry.start_time == timedelta(
        hours=1, minutes=30
    )
    assert moved.calendar_entry.title == "产品会议"
    assert moved.calendar_entry.participants == ["Alice"]
    assert moved.calendar_entry.timezone == "Asia/Shanghai"
    assert moved.calendar_entry.updated_by_run_id == update_run_id
    assert repeated.calendar_entry.start_time == moved.calendar_entry.start_time


async def test_reschedule_rejects_stale_selected_version(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    created = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="评审会",
            start_time="2026-07-11T10:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )
    selected = created.calendar_entry
    await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=selected.id,
            new_start_time="2026-07-12T10:00:00+08:00",
            expected_updated_at=selected.updated_at,
        ),
        updated_by_run_id=uuid4(),
    )

    with pytest.raises(CalendarEntryChangedError, match="changed after it was selected"):
        await reschedule_calendar_entry(
            db_session,
            tenant_context,
            RescheduleCalendarEntryInput(
                calendar_entry_id=selected.id,
                new_start_time="2026-07-13T10:00:00+08:00",
                expected_updated_at=selected.updated_at,
            ),
            updated_by_run_id=uuid4(),
        )


async def test_cancel_calendar_entry_is_soft_deleted_and_idempotent(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    created = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="客户会议",
            start_time="2026-07-11T08:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )
    run_id = uuid4()
    input_data = CancelCalendarEntryInput(
        calendar_entry_id=created.calendar_entry_id,
        expected_updated_at=created.calendar_entry.updated_at,
        reason="客户改期",
    )

    cancelled = await cancel_calendar_entry(
        db_session,
        tenant_context,
        input_data,
        cancelled_by_run_id=run_id,
    )
    repeated = await cancel_calendar_entry(
        db_session,
        tenant_context,
        input_data,
        cancelled_by_run_id=run_id,
    )
    repeated_in_another_run = await cancel_calendar_entry(
        db_session,
        tenant_context,
        input_data,
        cancelled_by_run_id=uuid4(),
    )

    assert cancelled.type == "calendar_entry_cancelled"
    assert cancelled.calendar_entry.cancelled_at is not None
    assert cancelled.calendar_entry.cancelled_by_run_id == run_id
    assert cancelled.calendar_entry.cancellation_reason == "客户改期"
    assert repeated.calendar_entry_id == cancelled.calendar_entry_id
    assert repeated_in_another_run.calendar_entry_id == cancelled.calendar_entry_id
    assert await list_calendar_entries(db_session, tenant_context) == []
    assert await search_calendar_entries(
        db_session,
        tenant_context,
        SearchCalendarEntriesInput(
            start_time="2026-07-11T00:00:00+08:00",
            end_time="2026-07-12T00:00:00+08:00",
        ),
    ) == []


async def test_cancel_rejects_stale_selected_version(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    created = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="评审会",
            start_time="2026-07-11T10:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )
    selected = created.calendar_entry
    await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=selected.id,
            new_date="2026-07-12",
            expected_updated_at=selected.updated_at,
        ),
        updated_by_run_id=uuid4(),
    )

    with pytest.raises(CalendarEntryChangedError, match="search again before cancelling"):
        await cancel_calendar_entry(
            db_session,
            tenant_context,
            CancelCalendarEntryInput(
                calendar_entry_id=selected.id,
                expected_updated_at=selected.updated_at,
            ),
            cancelled_by_run_id=uuid4(),
        )
