from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func
from north import make_checkpointer
import structlog

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import get_settings
from dayboard.context import TenantContext
from dayboard.db.session import SessionLocal
from dayboard.app.runs import AgentRunService
from dayboard.db.run_repositories import IdempotencyKeyRepository

logger = structlog.get_logger(__name__)


async def execute_command_run(
    ctx: dict[str, Any],
    run_id: str,
    context_data: dict[str, Any],
    request_data: dict[str, Any],
) -> None:
    context = TenantContext(
        tenant_id=UUID(context_data["tenant_id"]),
        user_id=UUID(context_data["user_id"]),
        timezone=context_data["timezone"],
        locale=context_data["locale"],
        isolation_mode=context_data.get("isolation_mode", "shared"),
    )
    request = CommandRequest.model_validate(request_data)
    async with SessionLocal() as session:
        await CommandService(
            session,
            checkpointer=ctx.get("checkpointer"),
        ).execute_command_run(context, request, UUID(run_id))


async def startup(ctx: dict[str, Any]) -> None:
    manager = make_checkpointer()
    ctx["checkpointer_manager"] = manager
    ctx["checkpointer"] = await manager.__aenter__()


async def shutdown(ctx: dict[str, Any]) -> None:
    manager = ctx.pop("checkpointer_manager", None)
    ctx.pop("checkpointer", None)
    if manager is not None:
        await manager.__aexit__(None, None, None)


async def recover_stale_command_runs(ctx: dict[str, Any]) -> None:
    del ctx
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.stale_run_seconds)
    async with SessionLocal() as session:
        recovered = await AgentRunService(session).recover_stale_running(
            updated_before=cutoff,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        await session.commit()
    if recovered:
        logger.warning(
            "dayboard.worker.stale_runs_recovered",
            count=len(recovered),
            run_ids=[str(run_id) for run_id in recovered],
        )


async def cleanup_expired_idempotency_keys(ctx: dict[str, Any]) -> None:
    del ctx
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.idempotency_retention_seconds)
    async with SessionLocal() as session:
        deleted = await IdempotencyKeyRepository(session).delete_created_before(cutoff)
        await session.commit()
    if deleted:
        logger.info("dayboard.worker.idempotency_keys_deleted", count=deleted)


settings = get_settings()


class WorkerSettings:
    on_startup = startup
    on_shutdown = shutdown
    functions = [func(execute_command_run, name="execute_command_run", max_tries=3, timeout=300)]
    redis_settings = RedisSettings.from_dsn(settings.effective_command_queue_url)
    queue_name = settings.command_queue_name
    max_jobs = 10
    health_check_interval = 15
    cron_jobs = [
        cron(recover_stale_command_runs, second={0, 30}, run_at_startup=True),
        cron(cleanup_expired_idempotency_keys, hour=3, minute=15),
    ]
