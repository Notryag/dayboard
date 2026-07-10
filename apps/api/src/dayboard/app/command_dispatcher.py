from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from dayboard.app.command_schemas import CommandRequest
from dayboard.app.commands import CommandService
from dayboard.context import TenantContext
from dayboard.db.session import SessionLocal

logger = structlog.get_logger(__name__)


class BackgroundCommandDispatcher:
    """Process queued Dayboard commands with request-independent database sessions."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    def start(self, run_id: UUID, context: TenantContext, request: CommandRequest) -> None:
        if run_id in self._tasks:
            raise RuntimeError(f"Run {run_id} is already scheduled")
        task = asyncio.create_task(
            self._execute(run_id, context, request),
            name=f"dayboard-command-{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    async def _execute(
        self,
        run_id: UUID,
        context: TenantContext,
        request: CommandRequest,
    ) -> None:
        try:
            async with self.session_factory() as session:
                await CommandService(session).execute_command_run(context, request, run_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("dayboard.command.background_execution_failed", run_id=str(run_id))

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
