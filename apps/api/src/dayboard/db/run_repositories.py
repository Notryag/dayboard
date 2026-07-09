from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import AgentRunEventRow, AgentRunRow
from dayboard.domain.runs import AgentRunEventCategory, AgentRunStatus


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: TenantContext,
        *,
        input_message: str,
        thread_id: UUID | None = None,
        status: AgentRunStatus = AgentRunStatus.queued,
    ) -> AgentRunRow:
        row = AgentRunRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            thread_id=thread_id or uuid4(),
            status=status.value,
            input_message=input_message,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_status(
        self,
        run: AgentRunRow,
        status: AgentRunStatus,
        *,
        result_message: str | None = None,
    ) -> AgentRunRow:
        run.status = status.value
        if result_message is not None:
            run.result_message = result_message
        await self.session.flush()
        return run

    async def get(self, context: TenantContext, run_id: UUID) -> AgentRunRow | None:
        return await self.session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.tenant_id == context.tenant_id,
                AgentRunRow.id == run_id,
                AgentRunRow.deleted_at.is_(None),
            )
        )


class AgentRunEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(
        self,
        context: TenantContext,
        *,
        run_id: UUID,
        event_type: str,
        category: AgentRunEventCategory,
        content: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> AgentRunEventRow:
        seq = await self._next_seq(context, run_id)
        row = AgentRunEventRow(
            tenant_id=context.tenant_id,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            category=category.value,
            content=content,
            event_metadata=event_metadata or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_run(self, context: TenantContext, run_id: UUID) -> list[AgentRunEventRow]:
        result = await self.session.scalars(
            select(AgentRunEventRow)
            .where(
                AgentRunEventRow.tenant_id == context.tenant_id,
                AgentRunEventRow.run_id == run_id,
            )
            .order_by(AgentRunEventRow.seq.asc())
        )
        return list(result)

    async def _next_seq(self, context: TenantContext, run_id: UUID) -> int:
        result = await self.session.scalar(
            select(func.coalesce(func.max(AgentRunEventRow.seq), 0) + 1).where(
                AgentRunEventRow.tenant_id == context.tenant_id,
                AgentRunEventRow.run_id == run_id,
            )
        )
        return int(result)
