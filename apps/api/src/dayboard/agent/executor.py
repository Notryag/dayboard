from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.app.command_schemas import CommandRequest, CommandResponse
from dayboard.config import Settings, get_settings
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

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        budget_guard: ProviderBudgetGuard | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.budget_guard = budget_guard or ProviderBudgetGuard(self.settings)

    async def execute(
        self,
        session: AsyncSession,
        context: TenantContext,
        request: CommandRequest,
    ) -> CommandResponse:
        del session
        estimate = self.budget_guard.estimate(input_text=request.message)
        self.budget_guard.check(
            context=context,
            model_name=self.settings.agent_model_name,
            estimate=estimate,
        )
        raise NotImplementedError("north command execution is not wired yet")
