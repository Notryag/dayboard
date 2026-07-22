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
    SearchTaskItemsInput,
    TaskItemChangedError,
    UpdateTaskItemInput,
    create_calendar_entry,
    cancel_calendar_entry,
    create_task_item,
    reschedule_calendar_entry,
    search_calendar_entries,
    search_task_items,
    update_task_item,
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

    entries = await search_calendar_entries(
        db_session,
        tenant_context,
        SearchCalendarEntriesInput(
            start_time="2026-07-10T00:00:00+08:00",
            end_time="2026-07-11T00:00:00+08:00",
        ),
    )

    assert result.type == "calendar_entry_created"
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

    overlaps = await search_calendar_entries(
        db_session,
        tenant_context,
        SearchCalendarEntriesInput(
            start_time=datetime(2026, 7, 11, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            end_time=datetime(2026, 7, 11, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        ),
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
    entries = await search_calendar_entries(
        db_session,
        tenant_context,
        SearchCalendarEntriesInput(
            start_time="2026-07-11T00:00:00+08:00",
            end_time="2026-07-12T00:00:00+08:00",
        ),
    )

    assert first.type == "calendar_entry_created"
    assert [entry.title for entry in overlaps] == ["晨会"]
    assert created_with_warning.type == "calendar_entry_created"
    assert [entry.title for entry in created_with_warning.conflicts] == ["晨会"]
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


async def test_calendar_creation_derives_time_from_locked_anchor(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    dance = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="跳舞",
            start_time="2026-07-23T09:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )

    singing = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="唱歌",
            timezone="Asia/Shanghai",
            anchor_entry_id=dance.calendar_entry.id,
            expected_anchor_updated_at=dance.calendar_entry.updated_at,
        ),
    )

    assert singing.calendar_entry.title == "唱歌"
    assert singing.calendar_entry.start_time == dance.calendar_entry.end_time
    assert singing.calendar_entry.end_time == dance.calendar_entry.end_time + timedelta(hours=1)
    assert singing.conflicts == []


async def test_calendar_anchor_rejects_stale_or_anytime_entry(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    dance = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="跳舞",
            start_time="2026-07-23T09:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )
    stale_updated_at = dance.calendar_entry.updated_at
    await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=dance.calendar_entry.id,
            new_start_time="2026-07-23T10:00:00+08:00",
            expected_updated_at=stale_updated_at,
        ),
        updated_by_run_id=uuid4(),
        operation_key="move-dance",
    )

    with pytest.raises(CalendarEntryChangedError, match="Anchor calendar entry changed"):
        await create_calendar_entry(
            db_session,
            tenant_context,
            CreateCalendarEntryInput(
                title="唱歌",
                timezone="Asia/Shanghai",
                anchor_entry_id=dance.calendar_entry.id,
                expected_anchor_updated_at=stale_updated_at,
            ),
        )

    anytime = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="提交报告",
            scheduled_date="2026-07-24",
            timezone="Asia/Shanghai",
        ),
    )
    with pytest.raises(ValueError, match="has no end time"):
        await create_calendar_entry(
            db_session,
            tenant_context,
            CreateCalendarEntryInput(
                title="庆祝",
                timezone="Asia/Shanghai",
                anchor_entry_id=anytime.calendar_entry.id,
                expected_anchor_updated_at=anytime.calendar_entry.updated_at,
            ),
        )


def test_calendar_input_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        CreateCalendarEntryInput(
            title="无时区会议",
            start_time=datetime(2026, 7, 11, 8, 0),
            timezone="Asia/Shanghai",
        )


def test_calendar_search_rejects_reversed_interval() -> None:
    with pytest.raises(ValidationError, match="start_time must be before end_time"):
        SearchCalendarEntriesInput(
            start_time="2026-07-11T10:00:00+08:00",
            end_time="2026-07-11T09:00:00+08:00",
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

    result = await search_calendar_entries(
        db_session,
        tenant_context,
        SearchCalendarEntriesInput(
            start_time=datetime.fromisoformat("2026-07-11T00:30:00+00:00"),
            end_time=datetime.fromisoformat("2026-07-11T01:00:00+00:00"),
        ),
    )

    assert [entry.title for entry in result] == ["上海会议"]


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

    tasks = await search_task_items(
        db_session,
        tenant_context,
        SearchTaskItemsInput(status=None),
    )

    assert result.type == "task_item_created"
    assert result.task_item.title == "整理周报"
    assert result.task_item.tenant_id == tenant_context.tenant_id
    assert result.task_item.owner_user_id == tenant_context.user_id
    assert tasks == [result.task_item]


async def test_empty_task_search_is_bounded(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    for index in range(52):
        await create_task_item(
            db_session,
            tenant_context,
            CreateTaskItemInput(title=f"任务 {index}", timezone="Asia/Shanghai"),
        )

    tasks = await search_task_items(
        db_session,
        tenant_context,
        SearchTaskItemsInput(status=None),
    )

    assert len(tasks) == 50


async def test_search_and_update_multiple_tasks_in_one_run(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    first = await create_task_item(
        db_session,
        tenant_context,
        CreateTaskItemInput(title="整理周报", timezone="Asia/Shanghai"),
    )
    second = await create_task_item(
        db_session,
        tenant_context,
        CreateTaskItemInput(title="提交报销", timezone="Asia/Shanghai"),
    )
    matches = await search_task_items(
        db_session,
        tenant_context,
        SearchTaskItemsInput(title_query="报"),
    )
    run_id = uuid4()
    completed = await update_task_item(
        db_session,
        tenant_context,
        UpdateTaskItemInput(
            task_item_id=first.task_item.id,
            expected_updated_at=first.task_item.updated_at,
            new_status="completed",
        ),
        updated_by_run_id=run_id,
        operation_key="complete-weekly-report",
    )
    moved = await update_task_item(
        db_session,
        tenant_context,
        UpdateTaskItemInput(
            task_item_id=second.task_item.id,
            expected_updated_at=second.task_item.updated_at,
            new_due_at="2026-07-13T18:00:00+08:00",
        ),
        updated_by_run_id=run_id,
        operation_key="move-expense-report",
    )
    repeated = await update_task_item(
        db_session,
        tenant_context,
        UpdateTaskItemInput(
            task_item_id=second.task_item.id,
            expected_updated_at=second.task_item.updated_at,
            new_due_at="2026-07-13T18:00:00+08:00",
        ),
        updated_by_run_id=run_id,
        operation_key="move-expense-report",
    )

    assert {task.id for task in matches} == {first.task_item.id, second.task_item.id}
    assert completed.task_item.status.value == "completed"
    assert moved.task_item.due_at is not None
    assert moved.task_item.updated_by_run_id == run_id
    assert repeated.task_item.id == moved.task_item.id


async def test_update_task_rejects_stale_selected_version(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    created = await create_task_item(
        db_session,
        tenant_context,
        CreateTaskItemInput(title="整理纪要", timezone="Asia/Shanghai"),
    )
    await update_task_item(
        db_session,
        tenant_context,
        UpdateTaskItemInput(
            task_item_id=created.task_item.id,
            expected_updated_at=created.task_item.updated_at,
            new_title="整理会议纪要",
        ),
        updated_by_run_id=uuid4(),
        operation_key="rename",
    )

    with pytest.raises(TaskItemChangedError, match="changed after it was selected"):
        await update_task_item(
            db_session,
            tenant_context,
            UpdateTaskItemInput(
                task_item_id=created.task_item.id,
                expected_updated_at=created.task_item.updated_at,
                new_status="cancelled",
            ),
            updated_by_run_id=uuid4(),
            operation_key="cancel",
        )


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
        operation_key="move-product-meeting",
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
        operation_key="move-product-meeting",
    )

    assert [entry.id for entry in matches] == [created.calendar_entry.id]
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
        operation_key="first-move",
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
            operation_key="stale-move",
        )


async def test_reschedule_can_change_only_end_time_and_rejects_noop(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    created = await create_calendar_entry(
        db_session,
        tenant_context,
        CreateCalendarEntryInput(
            title="吃饭",
            start_time="2026-07-14T12:00:00+08:00",
            end_time="2026-07-14T13:00:00+08:00",
            timezone="Asia/Shanghai",
        ),
    )

    extended = await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=created.calendar_entry.id,
            new_end_time="2026-07-14T17:00:00+08:00",
            expected_updated_at=created.calendar_entry.updated_at,
        ),
        updated_by_run_id=uuid4(),
        operation_key="extend-lunch",
    )

    assert extended.previous_start_time == created.calendar_entry.start_time
    assert extended.previous_end_time == created.calendar_entry.end_time
    assert extended.calendar_entry.start_time == created.calendar_entry.start_time
    assert extended.calendar_entry.end_time == datetime(
        2026, 7, 14, 17, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )

    with pytest.raises(ValueError, match="already has the requested time range"):
        await reschedule_calendar_entry(
            db_session,
            tenant_context,
            RescheduleCalendarEntryInput(
                calendar_entry_id=extended.calendar_entry.id,
                new_end_time="2026-07-14T17:00:00+08:00",
                expected_updated_at=extended.calendar_entry.updated_at,
            ),
            updated_by_run_id=uuid4(),
            operation_key="noop-extension",
        )


async def test_multiple_calendar_updates_and_cancellations_in_one_run(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    entries = []
    for index, title in enumerate(("晨会", "评审", "访谈", "复盘"), start=8):
        entries.append(
            (
                await create_calendar_entry(
                    db_session,
                    tenant_context,
                    CreateCalendarEntryInput(
                        title=title,
                        start_time=f"2026-07-11T{index:02d}:00:00+08:00",
                        timezone="Asia/Shanghai",
                    ),
                )
            ).calendar_entry
        )
    run_id = uuid4()

    first_move = await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=entries[0].id,
            new_date="2026-07-12",
            expected_updated_at=entries[0].updated_at,
        ),
        updated_by_run_id=run_id,
        operation_key="move-morning-meeting",
    )
    second_move = await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=entries[1].id,
            new_date="2026-07-13",
            expected_updated_at=entries[1].updated_at,
        ),
        updated_by_run_id=run_id,
        operation_key="move-review",
    )
    first_cancel = await cancel_calendar_entry(
        db_session,
        tenant_context,
        CancelCalendarEntryInput(
            calendar_entry_id=entries[2].id,
            expected_updated_at=entries[2].updated_at,
        ),
        cancelled_by_run_id=run_id,
        operation_key="cancel-interview",
    )
    second_cancel = await cancel_calendar_entry(
        db_session,
        tenant_context,
        CancelCalendarEntryInput(
            calendar_entry_id=entries[3].id,
            expected_updated_at=entries[3].updated_at,
        ),
        cancelled_by_run_id=run_id,
        operation_key="cancel-retrospective",
    )
    repeated_move = await reschedule_calendar_entry(
        db_session,
        tenant_context,
        RescheduleCalendarEntryInput(
            calendar_entry_id=entries[0].id,
            new_date="2026-07-12",
            expected_updated_at=entries[0].updated_at,
        ),
        updated_by_run_id=run_id,
        operation_key="move-morning-meeting",
    )

    assert first_move.calendar_entry.id == entries[0].id
    assert second_move.calendar_entry.id == entries[1].id
    assert repeated_move.calendar_entry.id == first_move.calendar_entry.id
    assert first_cancel.calendar_entry.id == entries[2].id
    assert second_cancel.calendar_entry.id == entries[3].id
    assert first_move.calendar_entry.updated_operation_key == "move-morning-meeting"
    assert second_cancel.calendar_entry.cancelled_operation_key == "cancel-retrospective"


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
        calendar_entry_id=created.calendar_entry.id,
        expected_updated_at=created.calendar_entry.updated_at,
        reason="客户改期",
    )

    cancelled = await cancel_calendar_entry(
        db_session,
        tenant_context,
        input_data,
        cancelled_by_run_id=run_id,
        operation_key="cancel-client-meeting",
    )
    repeated = await cancel_calendar_entry(
        db_session,
        tenant_context,
        input_data,
        cancelled_by_run_id=run_id,
        operation_key="cancel-client-meeting",
    )
    repeated_in_another_run = await cancel_calendar_entry(
        db_session,
        tenant_context,
        input_data,
        cancelled_by_run_id=uuid4(),
        operation_key="cancel-client-meeting-again",
    )

    assert cancelled.type == "calendar_entry_cancelled"
    assert cancelled.calendar_entry.cancelled_at is not None
    assert cancelled.calendar_entry.cancelled_by_run_id == run_id
    assert cancelled.calendar_entry.cancellation_reason == "客户改期"
    assert repeated.calendar_entry.id == cancelled.calendar_entry.id
    assert repeated_in_another_run.calendar_entry.id == cancelled.calendar_entry.id
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
        operation_key="move-before-cancel",
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
            operation_key="stale-cancel",
        )
