"""Application service for independent provider usage settlement."""

from __future__ import annotations

from agent_platform.core import TenantContext

from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageSettlement,
    ProviderUsageUnitOfWorkFactory,
)


class ProviderUsageService:
    def __init__(self, unit_of_work_factory: ProviderUsageUnitOfWorkFactory) -> None:
        self.unit_of_work_factory = unit_of_work_factory

    async def settle(
        self,
        context: TenantContext,
        aggregate: ProviderUsageAggregate,
    ) -> ProviderUsageSettlement:
        async with self.unit_of_work_factory() as unit_of_work:
            try:
                settlement = await unit_of_work.usage.settle(context, aggregate)
                await unit_of_work.commit()
                return settlement
            except BaseException:
                await unit_of_work.rollback()
                raise
