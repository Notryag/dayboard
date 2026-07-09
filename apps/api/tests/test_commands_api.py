from __future__ import annotations

from uuid import UUID

from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.run_repositories import AgentRunEventRepository


async def test_create_command_with_structured_calendar_entry(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/commands",
            json={
                "message": "周五上午 10 点和 Alice 做一次项目复盘。",
                "intent": "calendar_entry",
                "calendar_entry": {
                    "title": "项目复盘",
                    "start_time": "2026-07-10T10:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                    "participants": ["Alice"],
                },
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["result"]["type"] == "calendar_entry_created"
    assert body["result"]["calendar_entry"]["title"] == "项目复盘"
    assert body["result"]["calendar_entry"]["participants"] == ["Alice"]

    events = await AgentRunEventRepository(db_session).list_for_run(tenant_context, UUID(body["run_id"]))
    assert [event.event_type for event in events] == ["run_created", "run_started", "run_completed"]


async def test_get_run_and_events_after_command(api_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        create_response = await client.post(
            "/api/commands",
            json={"message": "帮我安排一下明天的事情"},
        )
        run_id = create_response.json()["run_id"]

        run_response = await client.get(f"/api/runs/{run_id}")
        events_response = await client.get(f"/api/runs/{run_id}/events")

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "needs_clarification"
    assert events_response.status_code == 200
    assert [event["event_type"] for event in events_response.json()] == [
        "run_created",
        "run_started",
        "clarification_requested",
    ]


async def test_create_command_without_structured_intent_needs_clarification(
    api_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/commands",
            json={"message": "帮我安排一下明天的事情"},
        )

    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "needs_clarification"
    assert body["result"] is None
    assert body["clarification_question"]
