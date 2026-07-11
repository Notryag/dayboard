from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func
from north import CheckpointerConfig, make_checkpointer
import structlog

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import get_settings
from dayboard.context import TenantContext
from dayboard.db.session import SessionLocal
from dayboard.app.runs import AgentRunService
from dayboard.db.run_repositories import IdempotencyKeyRepository
from dayboard.app.reminders import ReminderService

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
    manager = make_checkpointer(
        CheckpointerConfig(
            backend=settings.agent_checkpointer_backend,
            connection_string=settings.effective_checkpointer_database_url,
        )
    )
    ctx["checkpointer_manager"] = manager
    ctx["checkpointer"] = await manager.__aenter__()


async def shutdown(ctx: dict[str, Any]) -> None:
    manager = ctx.pop("checkpointer_manager", None)
    ctx.pop("checkpointer", None)
    if manager is not None:
        await manager.__aexit__(None, None, None)


async def recover_stale_command_runs(ctx: dict[str, Any]) -> None:
    del ctx
    now = datetime.now(UTC)
    running_cutoff = now - timedelta(seconds=settings.stale_run_seconds)
    queued_cutoff = now - timedelta(seconds=settings.queued_run_timeout_seconds)
    async with SessionLocal() as session:
        service = AgentRunService(session)
        recovered_running = await service.recover_stale_running(
            updated_before=running_cutoff,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        recovered_queued = await service.recover_stale_queued(
            created_before=queued_cutoff,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        await session.commit()
    if recovered_running or recovered_queued:
        logger.warning(
            "dayboard.worker.stale_runs_recovered",
            running_count=len(recovered_running),
            queued_count=len(recovered_queued),
            run_ids=[str(run_id) for run_id in recovered_running + recovered_queued],
        )


async def cleanup_expired_idempotency_keys(ctx: dict[str, Any]) -> None:
    del ctx
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.idempotency_retention_seconds)
    async with SessionLocal() as session:
        deleted = await IdempotencyKeyRepository(session).delete_created_before(cutoff)
        await session.commit()
    if deleted:
        logger.info("dayboard.worker.idempotency_keys_deleted", count=deleted)


async def deliver_due_reminders(ctx: dict[str, Any]) -> None:
    del ctx
    async with SessionLocal() as session:
        delivered_ids = await ReminderService(session).deliver_due_in_app()
    if delivered_ids:
        logger.info(
            "dayboard.worker.reminders_delivered",
            channel="in_app",
            count=len(delivered_ids),
            delivery_ids=delivered_ids,
        )


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
        cron(deliver_due_reminders, second={0, 15, 30, 45}, run_at_startup=True),
    ]
