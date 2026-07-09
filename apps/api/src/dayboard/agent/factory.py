from __future__ import annotations

from north import AppConfig, build_agent

from dayboard.agent.prompts import DAYBOARD_SYSTEM_PROMPT
from dayboard.config import Settings, get_settings


def build_dayboard_agent(settings: Settings | None = None, *, tools: list | None = None):
    resolved_settings = settings or get_settings()
    config = AppConfig(
        model_name=resolved_settings.agent_model_name,
        system_prompt=DAYBOARD_SYSTEM_PROMPT,
    )
    return build_agent(config, tools=tools or [])
