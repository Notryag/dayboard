from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import get_settings
from dayboard.context import TenantContext
from dayboard.db.session import SessionLocal
from dayboard.app.runs import AgentRunService


async def execute_command_run(
    ctx: dict[str, Any],
    run_id: str,
    context_data: dict[str, Any],
    request_data: dict[str, Any],
) -> None:
    del ctx
    context = TenantContext(
        tenant_id=UUID(context_data["tenant_id"]),
        user_id=UUID(context_data["user_id"]),
        timezone=context_data["timezone"],
        locale=context_data["locale"],
        isolation_mode=context_data.get("isolation_mode", "shared"),
    )
    request = CommandRequest.model_validate(request_data)
    async with SessionLocal() as session:
        await CommandService(session).execute_command_run(context, request, UUID(run_id))


async def recover_stale_command_runs(ctx: dict[str, Any]) -> None:
    del ctx
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.stale_run_seconds)
    async with SessionLocal() as session:
        await AgentRunService(session).recover_stale_running(
            updated_before=cutoff,
            timezone=settings.default_timezone,
            locale=settings.default_locale,
        )
        await session.commit()


settings = get_settings()


class WorkerSettings:
    functions = [func(execute_command_run, name="execute_command_run", max_tries=3, timeout=300)]
    redis_settings = RedisSettings.from_dsn(settings.effective_command_queue_url)
    queue_name = settings.command_queue_name
    max_jobs = 10
    health_check_interval = 15
    cron_jobs = [cron(recover_stale_command_runs, second={0, 30}, run_at_startup=True)]
