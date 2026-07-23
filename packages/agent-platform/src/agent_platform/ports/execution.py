"""Adapter port for product-specific Agent execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from agent_platform.core.execution import RunExecutionFailure, RunExecutionOutcome
from agent_platform.core.identity import TenantContext
from agent_platform.core.runs import AgentRun


RunCompletionCallback = Callable[[RunExecutionOutcome], Awaitable[None]]
RunFailureCallback = Callable[[RunExecutionFailure], Awaitable[bool]]


class RunExecutionDriver(Protocol):
    async def execute(
        self,
        context: TenantContext,
        run: AgentRun,
        *,
        on_completed: RunCompletionCallback,
        on_failed: RunFailureCallback,
    ) -> None: ...

    def failure_from_exception(self, exc: Exception) -> RunExecutionFailure: ...
