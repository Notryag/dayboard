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

    class FakeRunService:
        async def get_run_for_worker(self, requested_run_id):
            assert requested_run_id == run_id
            return SimpleNamespace(
                tenant_id=tenant_id,
                owner_user_id=user_id,
                input_message="数据库中的消息",
            )

    class FakeRunExecutionScope:
        def __init__(self) -> None:
            self.platform = SimpleNamespace(runs=FakeRunService())

        async def execute(self, context, requested_run_id):
            captured["context"] = context
            captured["run_id"] = requested_run_id

    scope = FakeRunExecutionScope()

    monkeypatch.setattr(
        "dayboard.workers.commands.SessionLocal",
        lambda: FakeSessionContext(),
    )
    monkeypatch.setattr(
        "dayboard.workers.commands.build_run_execution_scope",
        lambda session, **kwargs: (
            captured.update(session=session, **kwargs) or scope
        ),
    )

    await execute_command_run(
        {"checkpointer": "checkpoint", "redis": object()},
        str(run_id),
    )

    assert captured["context"].tenant_id == tenant_id
    assert captured["context"].user_id == user_id
    assert captured["run_id"] == run_id
    assert captured["session"] is not None
    assert captured["checkpointer"] == "checkpoint"
