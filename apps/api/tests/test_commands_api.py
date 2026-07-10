from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.runs import AgentRunService
from dayboard.api.routes import get_command_dispatcher
from dayboard.context import TenantContext
from dayboard.db.run_repositories import AgentRunEventRepository


async def test_create_background_command_run_returns_before_execution(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/command-runs",
            json={"message": "安排明天上午九点的项目会议"},
        )

    body = response.json()
    events = await AgentRunEventRepository(db_session).list_for_run(
        tenant_context,
        UUID(body["run_id"]),
    )
    dispatcher = api_app.state.test_command_dispatcher

    assert response.status_code == 202
    assert body["status"] == "queued"
    assert [event.event_type for event in events] == ["run_created"]
    assert dispatcher.started[0][0] == UUID(body["run_id"])
    assert dispatcher.started[0][2].message == "安排明天上午九点的项目会议"


async def test_get_queued_run_and_events_after_creation(api_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        create_response = await client.post(
            "/api/command-runs",
            json={"message": "帮我安排一下明天的事情"},
        )
        run_id = create_response.json()["run_id"]

        run_response = await client.get(f"/api/runs/{run_id}")
        events_response = await client.get(f"/api/runs/{run_id}/events")

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "queued"
    assert [event["event_type"] for event in events_response.json()] == ["run_created"]


async def test_command_run_creation_is_idempotent(api_app: FastAPI) -> None:
    headers = {"Idempotency-Key": "create-meeting-1"}
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/command-runs",
            headers=headers,
            json={"message": "安排会议"},
        )
        second = await client.post(
            "/api/command-runs",
            headers=headers,
            json={"message": "安排会议"},
        )

    dispatcher = api_app.state.test_command_dispatcher
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()
    assert len(dispatcher.started) == 1


async def test_idempotency_key_rejects_different_request(api_app: FastAPI) -> None:
    headers = {"Idempotency-Key": "create-meeting-2"}
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/command-runs",
            headers=headers,
            json={"message": "安排会议"},
        )
        conflict = await client.post(
            "/api/command-runs",
            headers=headers,
            json={"message": "安排任务"},
        )

    assert first.status_code == 202
    assert conflict.status_code == 409


async def test_queue_failure_marks_persisted_run_failed(api_app: FastAPI) -> None:
    class FailingDispatcher:
        def __init__(self) -> None:
            self.run_id = None

        async def enqueue(self, run_id, context, request) -> None:
            del context, request
            self.run_id = run_id
            raise ConnectionError("redis unavailable")

    dispatcher = FailingDispatcher()
    api_app.dependency_overrides[get_command_dispatcher] = lambda: dispatcher

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/command-runs",
            json={"message": "安排会议"},
        )
        run_response = await client.get(f"/api/runs/{dispatcher.run_id}")

    assert response.status_code == 503
    assert response.json()["detail"]["run_id"] == str(dispatcher.run_id)
    assert run_response.json()["status"] == "failed"
    assert run_response.json()["result_message"] == "redis unavailable"


async def test_stream_run_events_replays_events_and_closes_at_terminal_event(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    runs = AgentRunService(db_session)
    run = await runs.create_run(tenant_context, input_message="安排会议")
    await runs.mark_running(tenant_context, run)
    await runs.mark_needs_clarification(tenant_context, run, question="几点开始？")
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/events/stream?after_seq=1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 2\nevent: run_started\n" in response.text
    assert "id: 3\nevent: clarification_requested\n" in response.text
    assert "id: 1\n" not in response.text
    assert '"event_type":"clarification_requested"' in response.text


async def test_stream_run_events_returns_not_found(api_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{uuid4()}/events/stream")

    assert response.status_code == 404


async def test_stream_run_events_closes_when_cursor_is_past_terminal_event(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    runs = AgentRunService(db_session)
    run = await runs.create_run(tenant_context, input_message="安排会议")
    await runs.mark_running(tenant_context, run)
    await runs.mark_completed(tenant_context, run, result_message="已安排")
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/events/stream?after_seq=99")

    assert response.status_code == 200
    assert response.text == ""
