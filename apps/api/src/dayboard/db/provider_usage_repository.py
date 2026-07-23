from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
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

    async def settle(
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
    ) -> ProviderUsageSettlement:
        values = {
            "tenant_id": context.tenant_id,
            "owner_user_id": context.user_id,
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "usage_metadata": usage_metadata or {},
        }
        statement = insert(ProviderUsageRecordRow).values(**values)
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                ProviderUsageRecordRow.tenant_id,
                ProviderUsageRecordRow.run_id,
            ],
        ).returning(ProviderUsageRecordRow)
        row = await self.session.scalar(statement)
        if row is None:
            row = await self.session.scalar(
                select(ProviderUsageRecordRow).where(
                    ProviderUsageRecordRow.tenant_id == context.tenant_id,
                    ProviderUsageRecordRow.owner_user_id == context.user_id,
                    ProviderUsageRecordRow.run_id == run_id,
                )
            )
            if row is None:
                raise RuntimeError("Provider usage settlement returned no row")
            return ProviderUsageSettlement(row=row, created=False)
        return ProviderUsageSettlement(row=row, created=True)

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> list[ProviderUsageRecordRow]:
        rows = await self.session.scalars(
            select(ProviderUsageRecordRow)
            .where(
                ProviderUsageRecordRow.tenant_id == context.tenant_id,
                ProviderUsageRecordRow.owner_user_id == context.user_id,
                ProviderUsageRecordRow.run_id == run_id,
            )
            .order_by(ProviderUsageRecordRow.created_at.asc())
        )
        return list(rows)


@dataclass(frozen=True, slots=True)
class ProviderUsageSettlement:
    row: ProviderUsageRecordRow
    created: bool
