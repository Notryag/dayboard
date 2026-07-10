from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from north import AppConfig, build_agent
from north.tools.builtin import ask_clarification
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent.prompts import build_dayboard_system_prompt
from dayboard.agent.tools import build_scheduling_tools
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext


def build_dayboard_agent(
    settings: Settings | None = None,
    *,
    tools: list | None = None,
    session: AsyncSession | None = None,
    context: TenantContext | None = None,
    run_id: UUID | None = None,
    checkpointer=None,
    progress: Callable[[str, str, dict[str, Any]], Awaitable[None]] | None = None,
):
    resolved_settings = settings or get_settings()
    resolved_tools = tools
    if resolved_tools is None and session is not None and context is not None:
        resolved_tools = build_scheduling_tools(
            session=session,
            context=context,
            run_id=run_id,
            progress=progress,
        )
    resolved_tools = list(resolved_tools or [])
    if not any(getattr(tool, "name", None) == ask_clarification.name for tool in resolved_tools):
        resolved_tools.append(ask_clarification)

    config = AppConfig(
        model_name=resolved_settings.agent_model_name,
        system_prompt=build_dayboard_system_prompt(context or TenantContext(
            tenant_id=resolved_settings.default_tenant_id,
            user_id=resolved_settings.default_user_id,
            timezone=resolved_settings.default_timezone,
            locale=resolved_settings.default_locale,
        )),
    )
    return build_agent(config, tools=resolved_tools, checkpointer=checkpointer)
