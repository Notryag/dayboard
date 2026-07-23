from __future__ import annotations

from agent_platform.identity import TenantContext

from dayboard.config import get_settings


def get_dev_tenant_context() -> TenantContext:
    settings = get_settings()
    return TenantContext(
        tenant_id=settings.default_tenant_id,
        user_id=settings.default_user_id,
        timezone=settings.default_timezone,
        locale=settings.default_locale,
    )
