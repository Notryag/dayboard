from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import ProviderUsageRecordRow


class ProviderUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: TenantContext,
        *,
        run_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        usage_metadata: dict[str, Any] | None = None,
    ) -> ProviderUsageRecordRow:
        row = ProviderUsageRecordRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            run_id=run_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            usage_metadata=usage_metadata or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> list[ProviderUsageRecordRow]:
        rows = await self.session.scalars(
            select(ProviderUsageRecordRow)
            .where(
                ProviderUsageRecordRow.tenant_id == context.tenant_id,
                ProviderUsageRecordRow.run_id == run_id,
            )
            .order_by(ProviderUsageRecordRow.created_at.asc())
        )
        return list(rows)
