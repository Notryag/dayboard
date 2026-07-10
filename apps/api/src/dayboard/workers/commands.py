from __future__ import annotations

from typing import Any
from uuid import UUID

from arq.connections import RedisSettings
from arq.worker import func

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.config import get_settings
from dayboard.context import TenantContext
from dayboard.db.session import SessionLocal


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


settings = get_settings()


class WorkerSettings:
    functions = [func(execute_command_run, name="execute_command_run", max_tries=3, timeout=300)]
    redis_settings = RedisSettings.from_dsn(settings.effective_command_queue_url)
    queue_name = settings.command_queue_name
    max_jobs = 10
