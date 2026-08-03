from __future__ import annotations

from agent_platform.core import UserContext

from dayboard.config import get_settings


def get_dev_user_context() -> UserContext:
    settings = get_settings()
    return UserContext(
        user_id=settings.default_user_id,
        timezone=settings.default_timezone,
        locale=settings.default_locale,
    )
