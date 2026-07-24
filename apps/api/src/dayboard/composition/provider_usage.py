"""Composition root for independent provider usage settlement."""

from __future__ import annotations

from dayboard.app.provider_usage_ports import ProviderUsageSettlementPort
from dayboard.db.provider_usage_settlement import (
    SessionFactory,
    SqlAlchemyProviderUsageSettlement,
)
from dayboard.db.session import SessionLocal


def build_provider_usage_settlement(
    session_factory: SessionFactory = SessionLocal,
) -> ProviderUsageSettlementPort:
    return SqlAlchemyProviderUsageSettlement(session_factory)
