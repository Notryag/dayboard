from __future__ import annotations

from datetime import datetime
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
    entries = [
        CalendarEntryRow(
            tenant_id=tenant_context.tenant_id,
            owner_user_id=tenant_context.user_id,
            title=title,
            start_time=datetime(2026, 7, 13, hour, 0, tzinfo=timezone),
            end_time=datetime(2026, 7, 13, hour + 1, 0, tzinfo=timezone),
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
                start_time=datetime(2026, 7, 13, 9, 0, tzinfo=timezone),
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
                "from": "2026-07-13T00:00:00+08:00",
                "to": "2026-07-14T00:00:00+08:00",
                "limit": 1,
            },
        )
        second = await client.get(
            "/api/calendar-entries",
            params={
                "from": "2026-07-13T00:00:00+08:00",
                "to": "2026-07-14T00:00:00+08:00",
                "limit": 1,
                "cursor": first.json()["next_cursor"],
            },
        )
        today = await client.get("/api/calendar-entries", params={"period": "today"})

    assert first.status_code == 200
    assert [item["title"] for item in first.json()["items"]] == ["Morning"]
    assert first.json()["next_cursor"]
    assert [item["title"] for item in second.json()["items"]] == ["Afternoon"]
    assert second.json()["next_cursor"] is None
    assert [item["title"] for item in today.json()["items"]] == ["Today in account timezone"]
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

    assert [item["title"] for item in first.json()["items"]] == ["Due task"]
    assert [item["title"] for item in second.json()["items"]] == ["No due task"]
    assert [item["title"] for item in completed.json()["items"]] == ["Completed task"]


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

    assert naive.status_code == 422
    assert reversed_range.status_code == 422
    assert invalid_cursor.status_code == 422
