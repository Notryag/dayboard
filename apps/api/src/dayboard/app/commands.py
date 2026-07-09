from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent.executor import CommandExecutor, NorthCommandExecutor
from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.context import TenantContext


def get_command_executor() -> CommandExecutor:
    return NorthCommandExecutor()


class CommandService:
    def __init__(self, session: AsyncSession, executor: CommandExecutor | None = None) -> None:
        self.session = session
        self.executor = executor or get_command_executor()

    async def handle_command(
        self,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        return await self.executor.execute(self.session, context, request)
