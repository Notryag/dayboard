from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from north import AppConfig, build_agent
from north import CompactionHook
from north.tools.builtin import ask_clarification
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.agent.prompts import DAYBOARD_SUMMARY_PROMPT, build_dayboard_system_prompt
from dayboard.agent.tools import build_scheduling_tools
from dayboard.config import Settings, get_settings
from dayboard.context import TenantContext


TRUSTED_TOOL_CONTEXT_FIELDS = frozenset(
    {
        "tenant_id",
        "user_id",
        "owner_user_id",
        "timezone",
        "locale",
        "run_id",
        "thread_id",
        "request_id",
        "permissions",
    }
)


def _model_headers(
    settings: Settings,
    context: TenantContext | None,
    run_id: UUID | None,
) -> dict[str, str]:
    if not settings.northgate_metadata_enabled:
        return {}
    if context is None or run_id is None:
        raise ValueError("Northgate metadata requires trusted tenant context and run ID")
    metadata = {
        "tenant_id": str(context.tenant_id),
        "user_id": str(context.user_id),
        "run_id": str(run_id),
    }
    return {"Northgate-Metadata": json.dumps(metadata, separators=(",", ":"))}


def _validate_model_visible_tool_fields(tools: list) -> None:
    for tool in tools:
        fields = set(getattr(tool, "args", {}) or {})
        exposed = sorted(fields & TRUSTED_TOOL_CONTEXT_FIELDS)
        if exposed:
            name = getattr(tool, "name", type(tool).__name__)
            raise ValueError(
                f"Tool {name!r} exposes trusted server context to the model: "
                f"{', '.join(exposed)}"
            )


def build_dayboard_agent(
    settings: Settings | None = None,
    *,
    tools: list | None = None,
    session: AsyncSession | None = None,
    context: TenantContext | None = None,
    run_id: UUID | None = None,
    checkpointer=None,
    compaction_hooks: list[CompactionHook] | None = None,
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
    _validate_model_visible_tool_fields(resolved_tools)

    config = AppConfig(
        model_name=resolved_settings.agent_model_name,
        model_headers=_model_headers(resolved_settings, context, run_id),
        system_prompt=build_dayboard_system_prompt(context or TenantContext(
            tenant_id=resolved_settings.default_tenant_id,
            user_id=resolved_settings.default_user_id,
            timezone=resolved_settings.default_timezone,
            locale=resolved_settings.default_locale,
        )),
        summarization_enabled=resolved_settings.agent_summarization_enabled,
        summarization_model_name=resolved_settings.agent_summarization_model_name,
        summarization_summary_prompt=DAYBOARD_SUMMARY_PROMPT,
        summarization_trigger_messages=resolved_settings.agent_summarization_trigger_messages,
        summarization_keep_messages=resolved_settings.agent_summarization_keep_messages,
    )
    return build_agent(
        config,
        tools=resolved_tools,
        checkpointer=checkpointer,
        compaction_hooks=compaction_hooks,
    )
