from __future__ import annotations

from uuid import uuid4

from dayboard.app.command_dispatcher import RedisCommandDispatcher
from dayboard.app.command_schemas import CommandRequest
from dayboard.context import TenantContext


async def test_redis_dispatcher_enqueues_serializable_unique_job(
    tenant_context: TenantContext,
) -> None:
    captured = {}

    class FakeRedis:
        async def enqueue_job(self, function, *args, **kwargs):
            captured.update(function=function, args=args, kwargs=kwargs)
            return object()

    run_id = uuid4()
    dispatcher = RedisCommandDispatcher(FakeRedis(), queue_name="dayboard:test")

    await dispatcher.enqueue(run_id, tenant_context, CommandRequest(message="安排会议"))

    assert captured["function"] == "execute_command_run"
    assert captured["args"][0] == str(run_id)
    assert captured["args"][1]["tenant_id"] == str(tenant_context.tenant_id)
    assert captured["args"][2] == {"message": "安排会议"}
    assert captured["kwargs"]["_job_id"] == f"dayboard-command:{run_id}"
    assert captured["kwargs"]["_queue_name"] == "dayboard:test"


async def test_redis_dispatcher_rejects_duplicate_job(
    tenant_context: TenantContext,
) -> None:
    class FakeRedis:
        async def enqueue_job(self, function, *args, **kwargs):
            del function, args, kwargs
            return None

    run_id = uuid4()
    dispatcher = RedisCommandDispatcher(FakeRedis(), queue_name="dayboard:test")

    try:
        await dispatcher.enqueue(run_id, tenant_context, CommandRequest(message="安排会议"))
    except RuntimeError as exc:
        assert str(run_id) in str(exc)
    else:
        raise AssertionError("duplicate job should be rejected")
