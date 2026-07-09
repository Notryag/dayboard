from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI


async def test_create_command_with_structured_calendar_entry(api_app: FastAPI) -> None:
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
