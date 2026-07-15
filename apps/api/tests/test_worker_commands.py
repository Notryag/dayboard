from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from dayboard.workers.commands import execute_command_run


async def test_worker_restores_execution_context_from_persisted_run(monkeypatch) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    run_id = uuid4()
    captured = {}

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeRunRepository:
        def __init__(self, session):
            del session

        async def get_for_worker(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(
                tenant_id=tenant_id,
                owner_user_id=user_id,
                input_message="数据库中的消息",
            )

    class FakeCommandService:
        def __init__(self, session, *, checkpointer=None):
            captured["session"] = session
            captured["checkpointer"] = checkpointer

        async def execute_command_run(self, context, request, requested_run_id):
            captured["context"] = context
            captured["request"] = request
            captured["run_id"] = requested_run_id

    monkeypatch.setattr(
        "dayboard.workers.commands.SessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        "dayboard.workers.commands.AgentRunRepository",
        FakeRunRepository,
    )
    monkeypatch.setattr(
        "dayboard.workers.commands.CommandService",
        FakeCommandService,
    )

    await execute_command_run(
        {"checkpointer": "checkpoint"},
        str(run_id),
        {"tenant_id": str(uuid4()), "user_id": str(uuid4())},
        {"message": "队列中伪造的消息"},
    )

    assert captured["context"].tenant_id == tenant_id
    assert captured["context"].user_id == user_id
    assert captured["request"].message == "数据库中的消息"
    assert captured["run_id"] == run_id
    assert captured["checkpointer"] == "checkpoint"
