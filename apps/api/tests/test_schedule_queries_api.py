from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import CalendarEntryRow, TaskItemRow


async def test_calendar_query_filters_paginates_and_isolates_tenant(
    api_app,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    today_at_noon = datetime.now(timezone).replace(hour=12, minute=0, second=0, microsecond=0)
    scheduled_day = today_at_noon + timedelta(days=30)
    range_start = scheduled_day.replace(hour=0)
    range_end = range_start + timedelta(days=1)
    entries = [
        CalendarEntryRow(
            tenant_id=tenant_context.tenant_id,
            owner_user_id=tenant_context.user_id,
            title=title,
            start_time=scheduled_day.replace(hour=hour),
            end_time=scheduled_day.replace(hour=hour + 1),
            timezone="Asia/Shanghai",
            participants=[],
        )
        for title, hour in (("Morning", 8), ("Afternoon", 15))
    ]
    db_session.add_all(
        entries
        + [
            CalendarEntryRow(
                tenant_id=tenant_context.tenant_id,
                owner_user_id=tenant_context.user_id,
                title="Today in account timezone",
                start_time=today_at_noon,
                timezone="Asia/Shanghai",
                participants=[],
            ),
            CalendarEntryRow(
                tenant_id=uuid4(),
                owner_user_id=uuid4(),
                title="Another user",
                start_time=scheduled_day.replace(hour=9),
                timezone="Asia/Shanghai",
                participants=[],
            )
        ]
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        first = await client.get(
            "/api/calendar-entries",
            params={
                "from": range_start.isoformat(),
                "to": range_end.isoformat(),
                "limit": 1,
            },
        )
        second = await client.get(
            "/api/calendar-entries",
            params={
                "from": range_start.isoformat(),
                "to": range_end.isoformat(),
                "limit": 1,
                "cursor": first.json()["next_cursor"],
            },
        )
        today = await client.get("/api/calendar-entries", params={"period": "today"})
        selected_date = await client.get(
            "/api/calendar-entries",
            params={"date": scheduled_day.date().isoformat()},
        )

    assert first.status_code == 200
    assert [item["title"] for item in first.json()["items"]] == ["Morning"]
    assert first.json()["next_cursor"]
    assert [item["title"] for item in second.json()["items"]] == ["Afternoon"]
    assert second.json()["next_cursor"] is None
    assert [item["title"] for item in today.json()["items"]] == ["Today in account timezone"]
    assert [item["title"] for item in selected_date.json()["items"]] == [
        "Morning",
        "Afternoon",
    ]
    assert "tenant_id" not in first.json()["items"][0]
    assert "owner_user_id" not in first.json()["items"][0]


async def test_task_query_filters_status_due_range_and_paginates_null_due_last(
    api_app,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    db_session.add_all(
        [
            TaskItemRow(
                id=UUID("00000000-0000-0000-0000-000000000101"),
                tenant_id=tenant_context.tenant_id,
                owner_user_id=tenant_context.user_id,
                title="Due task",
                due_at=datetime(2026, 7, 13, 18, 0, tzinfo=timezone),
                timezone="Asia/Shanghai",
                status="open",
            ),
            TaskItemRow(
                id=UUID("00000000-0000-0000-0000-000000000102"),
                tenant_id=tenant_context.tenant_id,
                owner_user_id=tenant_context.user_id,
                title="No due task",
                due_at=None,
                timezone="Asia/Shanghai",
                status="open",
            ),
            TaskItemRow(
                tenant_id=tenant_context.tenant_id,
                owner_user_id=tenant_context.user_id,
                title="Completed task",
                due_at=datetime(2026, 7, 13, 12, 0, tzinfo=timezone),
                timezone="Asia/Shanghai",
                status="completed",
            ),
        ]
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        first = await client.get("/api/task-items", params={"status": "open", "limit": 1})
        second = await client.get(
            "/api/task-items",
            params={"status": "open", "limit": 1, "cursor": first.json()["next_cursor"]},
        )
        completed = await client.get("/api/task-items", params={"status": "completed"})
        undated = await client.get(
            "/api/task-items",
            params={"status": "open", "due_kind": "undated"},
        )
        selected_date = await client.get(
            "/api/task-items",
            params={"status": "open", "date": "2026-07-13"},
        )

    assert [item["title"] for item in first.json()["items"]] == ["Due task"]
    assert [item["title"] for item in second.json()["items"]] == ["No due task"]
    assert [item["title"] for item in completed.json()["items"]] == ["Completed task"]
    assert [item["title"] for item in undated.json()["items"]] == ["No due task"]
    assert [item["title"] for item in selected_date.json()["items"]] == ["Due task"]


async def test_schedule_queries_reject_invalid_ranges_and_cursors(api_app) -> None:
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        naive = await client.get("/api/calendar-entries", params={"from": "2026-07-13T08:00:00"})
        reversed_range = await client.get(
            "/api/task-items",
            params={
                "due_from": "2026-07-14T00:00:00+08:00",
                "due_to": "2026-07-13T00:00:00+08:00",
            },
        )
        invalid_cursor = await client.get("/api/calendar-entries", params={"cursor": "not-base64"})
        mixed_date_range = await client.get(
            "/api/calendar-entries",
            params={"date": "2026-07-13", "from": "2026-07-13T00:00:00+08:00"},
        )
        mixed_undated_range = await client.get(
            "/api/task-items",
            params={"due_kind": "undated", "due_from": "2026-07-13T00:00:00+08:00"},
        )
        mixed_task_date_range = await client.get(
            "/api/task-items",
            params={"date": "2026-07-13", "due_from": "2026-07-13T00:00:00+08:00"},
        )
        mixed_task_date_undated = await client.get(
            "/api/task-items",
            params={"date": "2026-07-13", "due_kind": "undated"},
        )

    assert naive.status_code == 422
    assert reversed_range.status_code == 422
    assert invalid_cursor.status_code == 422
    assert mixed_date_range.status_code == 422
    assert mixed_undated_range.status_code == 422
    assert mixed_task_date_range.status_code == 422
    assert mixed_task_date_undated.status_code == 422


async def test_run_schedule_items_and_direct_actions(
    api_app,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    run_id = UUID("00000000-0000-0000-0000-000000000201")
    entry = CalendarEntryRow(
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        title="游泳",
        start_time=datetime(2026, 7, 15, 19, 0, tzinfo=timezone),
        end_time=datetime(2026, 7, 15, 20, 0, tzinfo=timezone),
        timezone="Asia/Shanghai",
        participants=[],
        created_by_run_id=run_id,
    )
    cancelled_entry = CalendarEntryRow(
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        title="开会",
        start_time=datetime(2026, 7, 15, 21, 0, tzinfo=timezone),
        end_time=datetime(2026, 7, 15, 22, 0, tzinfo=timezone),
        timezone="Asia/Shanghai",
        participants=[],
        created_by_run_id=run_id,
    )
    task = TaskItemRow(
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        title="拿快递",
        due_at=None,
        timezone="Asia/Shanghai",
        status="open",
        created_by_run_id=run_id,
    )
    db_session.add_all(
        [
            entry,
            cancelled_entry,
            task,
            TaskItemRow(
                tenant_id=uuid4(),
                owner_user_id=uuid4(),
                title="Other account task",
                due_at=None,
                timezone="Asia/Shanghai",
                status="open",
                created_by_run_id=run_id,
            ),
        ]
    )
    await db_session.commit()
    await db_session.refresh(entry)
    await db_session.refresh(cancelled_entry)
    await db_session.refresh(task)
    original_task_updated_at = task.updated_at.isoformat()

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        completed = await client.post(
            f"/api/task-items/{task.id}/complete",
            json={"expected_updated_at": original_task_updated_at},
        )
        stale_cancel = await client.post(
            f"/api/task-items/{task.id}/cancel",
            json={"expected_updated_at": original_task_updated_at},
        )
        completed_entry = await client.post(
            f"/api/calendar-entries/{entry.id}/complete",
            json={"expected_updated_at": entry.updated_at.isoformat()},
        )
        repeated_completion = await client.post(
            f"/api/calendar-entries/{entry.id}/complete",
            json={"expected_updated_at": entry.updated_at.isoformat()},
        )
        completed_entry_cancel = await client.post(
            f"/api/calendar-entries/{entry.id}/cancel",
            json={"expected_updated_at": entry.updated_at.isoformat()},
        )
        reopened_task = await client.post(
            f"/api/task-items/{task.id}/reopen",
            json={"expected_updated_at": completed.json()["updated_at"]},
        )
        reopened_entry = await client.post(
            f"/api/calendar-entries/{entry.id}/reopen",
            json={"expected_updated_at": completed_entry.json()["updated_at"]},
        )
        cancelled = await client.post(
            f"/api/calendar-entries/{cancelled_entry.id}/cancel",
            json={"expected_updated_at": cancelled_entry.updated_at.isoformat()},
        )
        selected_date = await client.get(
            "/api/calendar-entries",
            params={"date": "2026-07-15"},
        )
        missing = await client.post(
            f"/api/calendar-entries/{uuid4()}/cancel",
            json={"expected_updated_at": cancelled_entry.updated_at.isoformat()},
        )

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert stale_cancel.status_code == 409
    assert stale_cancel.json()["error"]["code"] == "SCHEDULE_ITEM_CONFLICT"
    assert completed_entry.status_code == 200
    assert completed_entry.json()["status"] == "completed"
    assert repeated_completion.status_code == 200
    assert repeated_completion.json()["status"] == "completed"
    assert completed_entry_cancel.status_code == 409
    assert reopened_task.status_code == 200
    assert reopened_task.json()["status"] == "open"
    assert reopened_entry.status_code == 200
    assert reopened_entry.json()["status"] == "scheduled"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert [item["status"] for item in selected_date.json()["items"]] == ["scheduled"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CALENDAR_ENTRY_NOT_FOUND"


async def test_direct_schedule_item_updates(
    api_app,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    timezone = ZoneInfo("Asia/Shanghai")
    entry = CalendarEntryRow(
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        title="旧日程",
        start_time=datetime(2026, 7, 20, 9, 0, tzinfo=timezone),
        end_time=datetime(2026, 7, 20, 10, 0, tzinfo=timezone),
        timezone="Asia/Shanghai",
        participants=[],
    )
    task = TaskItemRow(
        tenant_id=tenant_context.tenant_id,
        owner_user_id=tenant_context.user_id,
        title="旧待办",
        due_at=datetime(2026, 7, 20, 18, 0, tzinfo=timezone),
        timezone="Asia/Shanghai",
        status="open",
    )
    db_session.add_all([entry, task])
    await db_session.commit()
    await db_session.refresh(entry)
    await db_session.refresh(task)
    entry_version = entry.updated_at.isoformat()

    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        updated_entry = await client.put(
            f"/api/calendar-entries/{entry.id}",
            json={
                "expected_updated_at": entry_version,
                "title": "新日程",
                "timing_kind": "timed",
                "start_time": "2026-07-21T14:30:00+08:00",
                "duration_minutes": 90,
            },
        )
        stale_entry = await client.put(
            f"/api/calendar-entries/{entry.id}",
            json={
                "expected_updated_at": entry_version,
                "title": "覆盖更新",
                "timing_kind": "timed",
                "start_time": "2026-07-21T15:00:00+08:00",
                "duration_minutes": 60,
            },
        )
        anytime_entry = await client.put(
            f"/api/calendar-entries/{entry.id}",
            json={
                "expected_updated_at": updated_entry.json()["updated_at"],
                "title": "随时日程",
                "timing_kind": "anytime",
                "scheduled_date": "2026-07-22",
            },
        )
        updated_task = await client.put(
            f"/api/task-items/{task.id}",
            json={
                "expected_updated_at": task.updated_at.isoformat(),
                "title": "新待办",
                "due_at": None,
            },
        )

    assert updated_entry.status_code == 200
    assert updated_entry.json()["title"] == "新日程"
    assert datetime.fromisoformat(updated_entry.json()["end_time"]) - datetime.fromisoformat(
        updated_entry.json()["start_time"]
    ) == timedelta(minutes=90)
    assert stale_entry.status_code == 409
    assert stale_entry.json()["error"]["code"] == "SCHEDULE_ITEM_CONFLICT"
    assert anytime_entry.status_code == 200
    assert anytime_entry.json()["timing_kind"] == "anytime"
    assert anytime_entry.json()["scheduled_date"] == "2026-07-22"
    assert anytime_entry.json()["start_time"] is None
    assert anytime_entry.json()["reminder"] is None
    assert updated_task.status_code == 200
    assert updated_task.json()["title"] == "新待办"
    assert updated_task.json()["due_at"] is None
