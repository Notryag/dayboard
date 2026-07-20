from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.runs import AgentRunService
from dayboard.app.conversations import ConversationService
from dayboard.api.routes import get_command_dispatcher
from dayboard.context import TenantContext
from dayboard.api.auth import get_tenant_context
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
    assert body["thread_id"]
    assert [event.event_type for event in events] == ["run_created"]
    assert dispatcher.started[0][0] == UUID(body["run_id"])
    assert dispatcher.started[0][2].message == "安排明天上午九点的项目会议"


async def test_thread_command_persists_user_message_once(
    api_app: FastAPI,
) -> None:
    headers = {"Idempotency-Key": "thread-message-1"}
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        thread_response = await client.post("/api/threads", json={"title": "工作安排"})
        thread_id = thread_response.json()["id"]
        first = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            headers=headers,
            json={"message": "明天上午开会"},
        )
        repeated = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            headers=headers,
            json={"message": "明天上午开会"},
        )
        messages = await client.get(f"/api/threads/{thread_id}/messages")

    assert thread_response.status_code == 201
    assert first.status_code == 202
    assert repeated.json() == first.json()
    assert first.json()["thread_id"] == thread_id
    assert [(message["role"], message["content"]) for message in messages.json()] == [
        ("user", "明天上午开会")
    ]


async def test_thread_rejects_a_second_active_run_and_allows_next_after_completion(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        thread = await client.post("/api/threads", json={"title": "工作安排"})
        thread_id = thread.json()["id"]
        first = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            json={"message": "创建明天的会议"},
        )
        second = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            json={"message": "再创建一个任务"},
        )

        runs = AgentRunService(db_session)
        first_row = await runs.get_run_row(tenant_context, UUID(first.json()["run_id"]))
        assert first_row is not None
        await runs.mark_running(tenant_context, first_row)
        await runs.mark_completed(tenant_context, first_row, result_message="会议已创建")
        await db_session.commit()

        third = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            json={"message": "再创建一个任务"},
        )
        messages = await client.get(f"/api/threads/{thread_id}/messages")

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "COMMAND_ALREADY_IN_PROGRESS"
    assert second.json()["error"]["request_id"].startswith("req_")
    assert third.status_code == 202
    assert [message["content"] for message in messages.json()] == [
        "创建明天的会议",
        "再创建一个任务",
    ]


async def test_active_thread_run_can_be_resumed_until_it_finishes(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        thread = await client.post("/api/threads", json={})
        thread_id = thread.json()["id"]
        created = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            json={"message": "创建明天的会议"},
        )
        active = await client.get(f"/api/threads/{thread_id}/active-run")

        runs = AgentRunService(db_session)
        run = await runs.get_run_row(tenant_context, UUID(created.json()["run_id"]))
        assert run is not None
        await runs.mark_running(tenant_context, run)
        await runs.mark_completed(tenant_context, run, result_message="会议已创建")
        await db_session.commit()

        finished = await client.get(f"/api/threads/{thread_id}/active-run")

    assert active.status_code == 200
    assert active.json()["id"] == created.json()["run_id"]
    assert active.json()["status"] == "queued"
    assert finished.status_code == 200
    assert finished.json() is None


async def test_active_thread_run_is_owner_scoped(
    api_app: FastAPI,
    tenant_context: TenantContext,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        thread = await client.post("/api/threads", json={})
        thread_id = thread.json()["id"]
        api_app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
            tenant_id=tenant_context.tenant_id,
            user_id=uuid4(),
            timezone=tenant_context.timezone,
            locale=tenant_context.locale,
        )
        response = await client.get(f"/api/threads/{thread_id}/active-run")

    assert response.status_code == 404


async def test_thread_routes_are_tenant_and_owner_scoped(
    api_app: FastAPI,
    tenant_context: TenantContext,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        created = await client.post("/api/threads", json={})
        thread_id = created.json()["id"]
        api_app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
            tenant_id=tenant_context.tenant_id,
            user_id=uuid4(),
            timezone=tenant_context.timezone,
            locale=tenant_context.locale,
        )
        messages = await client.get(f"/api/threads/{thread_id}/messages")
        command = await client.post(
            f"/api/threads/{thread_id}/command-runs",
            json={"message": "不能访问"},
        )

    assert messages.status_code == 404
    assert command.status_code == 404


async def test_structured_clarification_choice_creates_trusted_follow_up_run(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    conversations = ConversationService(db_session)
    thread = await conversations.create_thread(tenant_context, title="工作安排")
    source_run_id = uuid4()
    pending = await conversations.set_pending_clarification(
        tenant_context,
        thread_id=thread.id,
        run_id=source_run_id,
        question="你想修改哪一个日程？",
        state_data={
            "intent": "reschedule",
            "candidates": [
                {
                    "key": "candidate_1",
                    "id": "entry-secret-id",
                    "title": "产品会议",
                    "start_time": "2026-07-12T15:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                    "updated_at": "2026-07-11T01:00:00Z",
                }
            ],
            "interaction": {
                "type": "calendar_entry_choice",
                "options": [
                    {
                        "key": "candidate_1",
                        "title": "产品会议",
                        "start_time": "2026-07-12T15:00:00+08:00",
                        "timezone": "Asia/Shanghai",
                    }
                ],
            },
        },
    )
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/threads/{thread.id}/clarification-responses",
            headers={"Idempotency-Key": "choose-calendar-entry-1"},
            json={"state_version": pending.version, "option_key": "candidate_1"},
        )
        messages = await client.get(f"/api/threads/{thread.id}/messages")
        state = await client.get(f"/api/threads/{thread.id}/state")

    dispatcher = api_app.state.test_command_dispatcher
    queued_request = dispatcher.started[-1][2]
    assert response.status_code == 202
    assert response.json()["thread_id"] == str(thread.id)
    assert "entry-secret-id" in queued_request.message
    assert messages.json()[-1]["content"].startswith("选择“产品会议")
    assert "entry-secret-id" not in messages.json()[-1]["content"]
    assert "candidates" not in state.json()["state_data"]
    assert state.json()["state_data"]["interaction"]["options"][0]["key"] == "candidate_1"


async def test_structured_clarification_rejects_stale_state_version(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    conversations = ConversationService(db_session)
    thread = await conversations.create_thread(tenant_context)
    pending = await conversations.set_pending_clarification(
        tenant_context,
        thread_id=thread.id,
        run_id=uuid4(),
        question="选择一个日程",
        state_data={"candidates": [{"key": "candidate_1", "title": "会议"}]},
    )
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/threads/{thread.id}/clarification-responses",
            json={"state_version": pending.version + 1, "option_key": "candidate_1"},
        )

    assert response.status_code == 409
    assert "changed" in response.json()["error"]["message"]


async def test_health_checks_database_redis_and_worker(api_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.json()["redis"] == "ok"
    assert response.json()["worker"] == "ok"


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
    assert response.json()["error"]["code"] == "COMMAND_QUEUE_UNAVAILABLE"
    assert response.json()["error"]["details"]["run_id"] == str(dispatcher.run_id)
    assert run_response.json()["status"] == "failed"
    assert run_response.json()["result_message"] == "redis unavailable"


async def test_cancel_queued_run_is_persisted_and_dispatched(api_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/command-runs",
            json={"message": "安排会议"},
        )
        run_id = created.json()["run_id"]
        cancelled = await client.post(f"/api/runs/{run_id}/cancel")
        events = await client.get(f"/api/runs/{run_id}/events")

    dispatcher = api_app.state.test_command_dispatcher
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert [event["event_type"] for event in events.json()] == [
        "run_created",
        "run_cancelled",
    ]
    assert dispatcher.cancelled == [UUID(run_id)]


async def test_cancel_terminal_run_does_not_overwrite_status(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)
    run = await service.create_run(tenant_context, input_message="安排会议")
    await service.mark_running(tenant_context, run)
    await service.mark_completed(tenant_context, run, result_message="已安排")
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(f"/api/runs/{run.id}/cancel")
        events = await client.get(f"/api/runs/{run.id}/events")

    assert response.json()["status"] == "completed"
    assert [event["event_type"] for event in events.json()] == [
        "run_created",
        "run_started",
        "run_completed",
    ]


async def test_stream_run_events_returns_terminal_run_state(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    runs = AgentRunService(db_session)
    run = await runs.create_run(tenant_context, input_message="安排会议")
    await runs.mark_running(tenant_context, run)
    await runs.mark_needs_clarification(tenant_context, run, question="几点开始？")
    await ConversationService(db_session).upsert_assistant_message(
        tenant_context,
        thread_id=run.thread_id,
        run_id=run.id,
        content="几点开始？",
        message_metadata={
            "status": "needs_clarification",
            "parts": [{"tool_call_id": "call-1", "operation": "task_item_created"}],
        },
    )
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/events/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: clarification_requested\n" in response.text
    assert '"content": "几点开始？"' in response.text
    assert '"tool_call_id": "call-1"' in response.text


async def test_stream_run_events_returns_not_found(api_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{uuid4()}/events/stream")

    assert response.status_code == 404


async def test_stream_run_events_forwards_live_structured_messages(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    runs = AgentRunService(db_session)
    run = await runs.create_run(tenant_context, input_message="创建任务")
    await runs.mark_running(tenant_context, run)
    await db_session.commit()
    stream_bridge = api_app.state.test_stream_bridge
    await stream_bridge.publish(
        str(run.id),
        "messages-tuple",
        [
            {
                "type": "tool",
                "name": "create_task_item",
                "tool_call_id": "call-1",
                "content": {
                    "type": "task_item_created",
                    "task_item": {
                        "id": "task-1",
                        "title": "提交周报",
                        "due_at": None,
                        "timezone": "Asia/Shanghai",
                        "reminder": None,
                        "status": "open",
                        "created_by_run_id": str(run.id),
                        "created_at": "2026-07-20T10:00:00Z",
                        "updated_at": "2026-07-20T10:00:00Z",
                    },
                },
            },
            {},
        ],
    )
    await stream_bridge.publish(
        str(run.id), "run_completed", {"content": "任务已创建。"}
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/events/stream")

    assert response.status_code == 200
    assert "id: 1-0\nevent: schedule_item_result\n" in response.text
    assert '"tool_call_id":"call-1"' in response.text
    assert "id: 2-0\nevent: run_completed\n" in response.text


async def test_stream_run_events_drops_unprojected_canonical_and_raw_errors(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    runs = AgentRunService(db_session)
    run = await runs.create_run(tenant_context, input_message="执行内部工具")
    await runs.mark_running(tenant_context, run)
    await db_session.commit()
    stream_bridge = api_app.state.test_stream_bridge
    await stream_bridge.publish(
        str(run.id),
        "messages-tuple",
        [
            {
                "type": "tool",
                "name": "internal_admin_tool",
                "tool_call_id": "secret-call",
                "content": {"credential": "must-not-leak"},
            },
            {},
        ],
    )
    await stream_bridge.publish(
        str(run.id),
        "error",
        {"message": "provider secret", "error_type": "InternalError"},
    )
    await stream_bridge.publish(
        str(run.id), "run_failed", {"content": "请求没有成功。"}
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/events/stream")

    assert response.status_code == 200
    assert "must-not-leak" not in response.text
    assert "provider secret" not in response.text
    assert "event: run_failed\n" in response.text


async def test_stream_run_events_resumes_from_last_event_id_header(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    runs = AgentRunService(db_session)
    run = await runs.create_run(tenant_context, input_message="继续事件流")
    await runs.mark_running(tenant_context, run)
    await db_session.commit()
    stream_bridge = api_app.state.test_stream_bridge
    await stream_bridge.publish(str(run.id), "run_started", {"content": "开始"})
    await stream_bridge.publish(
        str(run.id), "run_completed", {"content": "完成"}
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/api/runs/{run.id}/events/stream",
            headers={"Last-Event-ID": "1-0"},
        )

    assert response.status_code == 200
    assert "event: run_started\n" not in response.text
    assert "id: 2-0\nevent: run_completed\n" in response.text


async def test_stream_run_events_rejects_invalid_last_event_id(
    api_app: FastAPI,
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    run = await AgentRunService(db_session).create_run(
        tenant_context, input_message="无效游标"
    )
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/api/runs/{run.id}/events/stream",
            headers={"Last-Event-ID": "not-a-redis-id"},
        )

    assert response.status_code == 422


async def test_stream_run_events_ignores_live_cursor_for_terminal_run(
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
        response = await client.get(f"/api/runs/{run.id}/events/stream?after=99-0")

    assert response.status_code == 200
    assert "event: run_completed\n" in response.text
    assert '"content": "已安排"' in response.text
