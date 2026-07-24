from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func
from north import CheckpointerConfig, make_checkpointer
from north.runtime import RedisStreamBridge
import structlog

from dayboard.app.commands import CommandService
from dayboard.composition.reminders import build_reminder_services
from dayboard.app.run_recovery import recover_stale_queued_runs, recover_stale_running_runs
from dayboard.app.platform_services import (
    build_idempotency_service,
    build_platform_services,
    build_run_service,
)
from dayboard.config import get_settings
from agent_platform.core import TenantContext
from dayboard.db.session import SessionLocal

logger = structlog.get_logger(__name__)


async def execute_command_run(
    ctx: dict[str, Any],
    run_id: str,
) -> None:
    resolved_run_id = UUID(run_id)
    async with SessionLocal() as session:
        run = await build_run_service(session).get_run_for_worker(resolved_run_id)
        if run is None:
            raise LookupError(f"Run {resolved_run_id} not found")
        context = TenantContext(
            tenant_id=run.tenant_id,
            user_id=run.owner_user_id,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        await CommandService(
            session,
            checkpointer=ctx.get("checkpointer"),
            stream_bridge=RedisStreamBridge(
                ctx["redis"],
                key_prefix="dayboard:run-stream",
            ),
        ).execute_command_run(context, resolved_run_id)


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
        platform = build_platform_services(session)
        service = platform.runs
        recovered_running = await recover_stale_running_runs(
            service,
            updated_before=running_cutoff,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        recovered_queued = await recover_stale_queued_runs(
            service,
            created_before=queued_cutoff,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        await platform.unit_of_work.commit()
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
        deleted = await build_idempotency_service(session).delete_created_before(cutoff)
    if deleted:
        logger.info("dayboard.worker.idempotency_keys_deleted", count=deleted)


async def deliver_due_reminders(ctx: dict[str, Any]) -> None:
    del ctx
    async with SessionLocal() as session:
        scope = build_reminder_services(session)
        result = await scope.reminders.process_due_in_app()
        await scope.unit_of_work.commit()
    if result.delivered_ids or result.expired_ids or result.cancelled_ids:
        logger.info(
            "dayboard.worker.reminders_processed",
            channel="in_app",
            delivered_count=len(result.delivered_ids),
            delivered_ids=[str(delivery_id) for delivery_id in result.delivered_ids],
            expired_count=len(result.expired_ids),
            expired_ids=[str(delivery_id) for delivery_id in result.expired_ids],
            cancelled_count=len(result.cancelled_ids),
            cancelled_ids=[str(delivery_id) for delivery_id in result.cancelled_ids],
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
