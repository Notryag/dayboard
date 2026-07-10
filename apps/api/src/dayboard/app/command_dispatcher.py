from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from arq.connections import ArqRedis
from arq.jobs import Job

from dayboard.app.command_schemas import CommandRequest
from dayboard.context import TenantContext


class RedisCommandDispatcher:
    """Enqueue command runs for execution by an arq worker."""

    def __init__(self, redis: ArqRedis, *, queue_name: str) -> None:
        self.redis = redis
        self.queue_name = queue_name

    async def enqueue(
        self,
        run_id: UUID,
        context: TenantContext,
        request: CommandRequest,
    ) -> None:
        job = await self.redis.enqueue_job(
            "execute_command_run",
            str(run_id),
            {key: str(value) if isinstance(value, UUID) else value for key, value in asdict(context).items()},
            request.model_dump(mode="json"),
            _job_id=f"dayboard-command:{run_id}",
            _queue_name=self.queue_name,
        )
        if job is None:
            raise RuntimeError(f"Run {run_id} is already queued")

    async def cancel(self, run_id: UUID) -> bool:
        job = Job(
            f"dayboard-command:{run_id}",
            self.redis,
            _queue_name=self.queue_name,
        )
        return await job.abort(timeout=2)

    async def health(self) -> dict[str, bool]:
        redis_ok = bool(await self.redis.ping())
        worker_ok = bool(await self.redis.get(f"{self.queue_name}:health-check"))
        return {"redis": redis_ok, "worker": worker_ok}
