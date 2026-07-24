"""Independent transaction adapter for provider usage settlement."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageSettlement,
)
from dayboard.db.provider_usage_repository import ProviderUsageRepository


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class SqlAlchemyProviderUsageSettlement:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def settle(
        self,
        context: TenantContext,
        aggregate: ProviderUsageAggregate,
    ) -> ProviderUsageSettlement:
        async with self._session_factory() as session:
            repository = ProviderUsageRepository(session)
            try:
                settlement = await repository.settle(context, aggregate)
                await session.commit()
                return settlement
            except BaseException:
                await session.rollback()
                raise
