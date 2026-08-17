from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from north import FunctionPlugin, PluginContext, RegistrationHandle

from dayboard.agent.middleware import SchedulingToolBindingMiddleware


def _register_tools(context: PluginContext, tools: Sequence[Any]) -> RegistrationHandle | None:
    handles = [context.register_tool(tool) for tool in tools]
    return RegistrationHandle(lambda: [handle.dispose() for handle in reversed(handles)])


def build_dayboard_plugins(
    *,
    tools: Sequence[Any],
    runtime_context: dict[str, Any],
) -> tuple[FunctionPlugin, ...]:
    """Compose Dayboard's lead-agent plugins."""

    def install_tools(context: PluginContext) -> RegistrationHandle | None:
        return _register_tools(context, tools)

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
