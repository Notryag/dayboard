from __future__ import annotations

import json

import httpx

from dayboard.eval_state import reset_active_schedule


async def test_eval_reset_cancels_active_schedule_through_versioned_apis() -> None:
    requests: list[tuple[str, str, dict[str, str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, dict(request.url.params)))
        if request.method == "GET" and request.url.path == "/api/calendar-entries":
            assert request.url.params["status"] == "scheduled"
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "calendar-1", "row_version": 3}],
                    "next_cursor": None,
                },
            )
        if request.method == "POST" and request.url.path == "/api/calendar-entries/calendar-1/cancel":
            assert json.loads(request.read()) == {"expected_row_version": 3}
            return httpx.Response(200, json={})
        if request.method == "GET" and request.url.path == "/api/task-items":
            assert request.url.params["status"] == "open"
            assert request.url.params["due_kind"] == "all"
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "task-1", "row_version": 7}],
                    "next_cursor": None,
                },
            )
        if request.method == "POST" and request.url.path == "/api/task-items/task-1/cancel":
            assert json.loads(request.read()) == {"expected_row_version": 7}
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await reset_active_schedule(client)

    assert result == {
        "performed": True,
        "calendar_entries_cancelled": 1,
        "task_items_cancelled": 1,
    }
    assert len(requests) == 4


async def test_eval_reset_follows_schedule_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/calendar-entries":
            cursor = request.url.params.get("cursor")
            return httpx.Response(
                200,
                json={
                    "items": [{"id": f"calendar-{cursor or 'first'}", "row_version": 1}],
                    "next_cursor": "page-2" if cursor is None else None,
                },
            )
        if request.method == "GET" and request.url.path == "/api/task-items":
            return httpx.Response(200, json={"items": [], "next_cursor": None})
        if request.method == "POST" and request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await reset_active_schedule(client)

    assert result["calendar_entries_cancelled"] == 2
