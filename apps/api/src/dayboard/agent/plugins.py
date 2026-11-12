from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from north import FunctionPlugin, PluginContext, RegistrationHandle

from dayboard.agent.middleware import SchedulingToolBindingMiddleware
from dayboard.agent.clarification_candidates import RunClarificationCandidates


def _register_tools(context: PluginContext, tools: Sequence[Any]) -> RegistrationHandle | None:
    handles = [context.register_tool(tool) for tool in tools]

    def dispose() -> None:
        for handle in reversed(handles):
            handle.dispose()

    return RegistrationHandle(dispose)


def build_dayboard_plugins(
    *,
    tools: Sequence[Any],
    runtime_context: str,
    clarification_candidates: RunClarificationCandidates | None = None,
) -> tuple[FunctionPlugin, ...]:
    """Compose Dayboard's lead-agent plugins."""

    def install_tools(context: PluginContext) -> RegistrationHandle | None:
        resolved_tools = list(tools)
        replaced = []
        if clarification_candidates is not None:
            # North installs its runtime tools first. Replace only the interaction
            # tool schema; its generic typed clarification middleware still runs.
            replaced = [
                tool for tool in context.tools if getattr(tool, "name", None) == "ask_clarification"
            ]
            context.tools[:] = [tool for tool in context.tools if tool not in replaced]
            resolved_tools = [
                tool
                for tool in resolved_tools
                if getattr(tool, "name", None) != "ask_clarification"
            ]
            resolved_tools.append(clarification_candidates.build_tool())
        handle = _register_tools(context, resolved_tools)

        def dispose() -> None:
            if handle is not None:
                handle.dispose()
            context.tools.extend(replaced)

        return RegistrationHandle(dispose)

    def install_scheduling(context: PluginContext) -> RegistrationHandle:
        return context.register_middleware(
            SchedulingToolBindingMiddleware(runtime_context=runtime_context)
        )

    return (
        FunctionPlugin(
            plugin_id="dayboard.tools",
            installer=install_tools,
            requires=("north.runtime",),
            scopes=("lead_agent",),
        ),
        FunctionPlugin(
            plugin_id="dayboard.scheduling",
            installer=install_scheduling,
            requires=("north.runtime",),
            scopes=("lead_agent",),
        ),
    )


__all__ = ["build_dayboard_plugins"]
