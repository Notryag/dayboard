from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.runs import AgentRunService
from dayboard.context import TenantContext
from dayboard.db.run_repositories import AgentRunEventRepository
from dayboard.domain.runs import AgentRunStatus


async def test_agent_run_service_records_lifecycle_events(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    service = AgentRunService(db_session)

    run = await service.create_run(tenant_context, input_message="安排明天的事情")
    await service.mark_running(tenant_context, run)
    await service.mark_needs_clarification(tenant_context, run, question="需要几点？")
    await db_session.commit()
    await db_session.refresh(run)

    events = await AgentRunEventRepository(db_session).list_for_run(tenant_context, run.id)

    assert run.status == AgentRunStatus.needs_clarification.value
    assert [event.seq for event in events] == [1, 2, 3]
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "clarification_requested",
    ]
    assert events[-1].content == "需要几点？"
