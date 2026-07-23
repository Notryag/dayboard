from __future__ import annotations

from uuid import uuid4

from dayboard.app.command_dispatcher import RedisCommandDispatcher
async def test_redis_dispatcher_enqueues_serializable_unique_job(
) -> None:
    captured = {}

    class FakeRedis:
        async def enqueue_job(self, function, *args, **kwargs):
            captured.update(function=function, args=args, kwargs=kwargs)
            return object()

    run_id = uuid4()
    dispatcher = RedisCommandDispatcher(FakeRedis(), queue_name="dayboard:test")

    await dispatcher.enqueue(run_id)

    assert captured["function"] == "execute_command_run"
    assert captured["args"][0] == str(run_id)
    assert captured["args"] == (str(run_id),)
    assert captured["kwargs"]["_job_id"] == f"dayboard-command:{run_id}"
    assert captured["kwargs"]["_queue_name"] == "dayboard:test"


async def test_redis_dispatcher_rejects_duplicate_job(
) -> None:
    class FakeRedis:
        async def enqueue_job(self, function, *args, **kwargs):
            del function, args, kwargs
            return None

    run_id = uuid4()
    dispatcher = RedisCommandDispatcher(FakeRedis(), queue_name="dayboard:test")

    try:
        await dispatcher.enqueue(run_id)
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


async def test_redis_dispatcher_reports_worker_health() -> None:
    class FakeRedis:
        async def ping(self):
            return True

        async def get(self, key):
            assert key == "dayboard:test:health-check"
            return b"healthy"

    dispatcher = RedisCommandDispatcher(FakeRedis(), queue_name="dayboard:test")

    assert await dispatcher.health() == {"redis": True, "worker": True}
