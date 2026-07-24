"""Composition for one Dayboard North execution driver and its Platform scope."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from north import CompactionHook, RunExecutor
from north.runtime import StreamBridge
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
from agent_platform.ports import PlatformUnitOfWorkFactory
from dayboard.agent.budget import ProviderBudgetGuard
from dayboard.agent.factory import build_dayboard_agent
from dayboard.agent.run_execution import (
    DayboardAgentFactory,
    DayboardRunExecutionDriver,
    RunExecutorFactory,
)
from dayboard.app.provider_usage import ProviderUsageService
from dayboard.composition.platform import (
    PlatformServiceScope,
    build_platform_services,
    build_platform_unit_of_work_factory,
)
from dayboard.composition.provider_usage import build_provider_usage_service
from dayboard.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class RunExecutionScope:
    platform: PlatformServiceScope
    driver: DayboardRunExecutionDriver

    async def execute(self, context: TenantContext, run_id: UUID) -> None:
        await self.platform.execution.execute(context, run_id, self.driver)


def build_dayboard_agent_factory(
    settings: Settings,
    session: AsyncSession,
    *,
    checkpointer: object | None = None,
) -> DayboardAgentFactory:
    def create_agent(
        context: TenantContext,
        run_id: UUID,
        compaction_hooks: Sequence[CompactionHook],
    ) -> object:
        return build_dayboard_agent(
            settings,
            session=session,
            context=context,
            run_id=run_id,
            checkpointer=checkpointer,
            compaction_hooks=list(compaction_hooks),
        )

    return create_agent


def build_run_execution_scope(
    session: AsyncSession,
    *,
    stream_bridge: StreamBridge,
    settings: Settings | None = None,
    budget_guard: ProviderBudgetGuard | None = None,
    provider_usage: ProviderUsageService | None = None,
    checkpointer: object | None = None,
    runtime_event_uow_factory: PlatformUnitOfWorkFactory | None = None,
    executor_factory: RunExecutorFactory = RunExecutor,
) -> RunExecutionScope:
    resolved_settings = settings or get_settings()
    platform = build_platform_services(session)
    driver = DayboardRunExecutionDriver(
        unit_of_work=platform.unit_of_work,
        conversations=platform.conversations,
        runs=platform.runs,
        budget_guard=budget_guard or ProviderBudgetGuard(resolved_settings),
        provider_usage=provider_usage or build_provider_usage_service(),
        runtime_event_uow_factory=(
            runtime_event_uow_factory or build_platform_unit_of_work_factory()
        ),
        agent_factory=build_dayboard_agent_factory(
            resolved_settings,
            session,
            checkpointer=checkpointer,
        ),
        model_name=resolved_settings.agent_model_name,
        stream_bridge=stream_bridge,
        executor_factory=executor_factory,
    )
    return RunExecutionScope(
        platform=platform,
        driver=driver,
    )
