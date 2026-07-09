from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.context import TenantContext


class CommandExecutor(Protocol):
    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        """Execute a command and return the user-facing result."""


class NorthCommandExecutor:
    """Future north-backed executor.

    This class marks the integration boundary. It intentionally does not
    execute model calls yet because Dayboard still needs provider budgets,
    LangChain tool wrappers with injected DB/session context, and clarification
    event mapping before replacing the placeholder flow.
    """

    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        del session, context, request
        raise NotImplementedError("north command execution is not wired yet")
