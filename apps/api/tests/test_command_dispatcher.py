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


async def test_redis_dispatcher_aborts_run_job(tenant_context, monkeypatch) -> None:
    captured = {}

    class FakeJob:
        def __init__(self, job_id, redis, _queue_name):
            captured.update(job_id=job_id, redis=redis, queue_name=_queue_name)

        async def abort(self, *, timeout):
            captured["timeout"] = timeout
            return True

    monkeypatch.setattr("dayboard.app.command_dispatcher.Job", FakeJob)
    redis = object()
    dispatcher = RedisCommandDispatcher(redis, queue_name="dayboard:test")
    run_id = uuid4()

    assert await dispatcher.cancel(run_id) is True
    assert captured == {
        "job_id": f"dayboard-command:{run_id}",
        "redis": redis,
        "queue_name": "dayboard:test",
        "timeout": 2,
    }
