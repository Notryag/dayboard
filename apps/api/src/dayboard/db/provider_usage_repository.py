from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, bindparam, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID, insert
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext
from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageCall,
    ProviderUsageRunNotFound,
    ProviderUsageSettlement,
)
from dayboard.db.models import AgentRunRow, ProviderUsageRecordRow


def _serialize_calls(calls: tuple[ProviderUsageCall, ...]) -> dict[str, Any]:
    return {
        "calls": [
            {
                "call_id": call.call_id,
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
                "total_tokens": call.total_tokens,
            }
            for call in calls
        ]
    }


def _deserialize_calls(metadata: Mapping[str, Any]) -> tuple[ProviderUsageCall, ...]:
    raw_calls = metadata.get("calls", [])
    if not isinstance(raw_calls, list):
        raise ValueError("Provider usage calls metadata must be a list")
    calls: list[ProviderUsageCall] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, Mapping):
            raise ValueError("Provider usage call metadata must be an object")
        calls.append(
            ProviderUsageCall(
                call_id=str(raw_call["call_id"]),
                input_tokens=int(raw_call["input_tokens"]),
                output_tokens=int(raw_call["output_tokens"]),
                total_tokens=int(raw_call["total_tokens"]),
            )
        )
    return tuple(calls)


class ProviderUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def settle(
        self,
        context: TenantContext,
        aggregate: ProviderUsageAggregate,
    ) -> ProviderUsageSettlement:
        source = select(
            bindparam("usage_record_id", uuid4(), type_=PostgresUUID(as_uuid=True)),
            AgentRunRow.tenant_id,
            AgentRunRow.owner_user_id,
            AgentRunRow.id,
            bindparam("provider", aggregate.provider, type_=String(80)),
            bindparam("model", aggregate.model, type_=String(240)),
            bindparam("input_tokens", aggregate.input_tokens, type_=Integer()),
            bindparam("output_tokens", aggregate.output_tokens, type_=Integer()),
            bindparam("total_tokens", aggregate.total_tokens, type_=Integer()),
            bindparam("usage_metadata", _serialize_calls(aggregate.calls), type_=JSONB()),
        ).where(
            AgentRunRow.id == aggregate.run_id,
            AgentRunRow.tenant_id == context.tenant_id,
            AgentRunRow.owner_user_id == context.user_id,
            AgentRunRow.deleted_at.is_(None),
        )
        statement = insert(ProviderUsageRecordRow).from_select(
            [
                ProviderUsageRecordRow.id,
                ProviderUsageRecordRow.tenant_id,
                ProviderUsageRecordRow.owner_user_id,
                ProviderUsageRecordRow.run_id,
                ProviderUsageRecordRow.provider,
                ProviderUsageRecordRow.model,
                ProviderUsageRecordRow.input_tokens,
                ProviderUsageRecordRow.output_tokens,
                ProviderUsageRecordRow.total_tokens,
                ProviderUsageRecordRow.usage_metadata,
            ],
            source,
        )
        statement = statement.on_conflict_do_nothing(
            index_elements=[
                ProviderUsageRecordRow.tenant_id,
                ProviderUsageRecordRow.run_id,
            ],
        ).returning(ProviderUsageRecordRow.id)
        created_id = await self._session.scalar(statement)
        if created_id is not None:
            return ProviderUsageSettlement(created=True)

        existing_id = await self._session.scalar(
            select(ProviderUsageRecordRow.id).where(
                ProviderUsageRecordRow.tenant_id == context.tenant_id,
                ProviderUsageRecordRow.owner_user_id == context.user_id,
                ProviderUsageRecordRow.run_id == aggregate.run_id,
            )
        )
        if existing_id is None:
            raise ProviderUsageRunNotFound(
                f"Run {aggregate.run_id} is not visible to the provider usage context"
            )
        return ProviderUsageSettlement(created=False)

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> list[ProviderUsageAggregate]:
        rows = (
            await self._session.execute(
                select(
                    ProviderUsageRecordRow.run_id,
                    ProviderUsageRecordRow.provider,
                    ProviderUsageRecordRow.model,
                    ProviderUsageRecordRow.input_tokens,
                    ProviderUsageRecordRow.output_tokens,
                    ProviderUsageRecordRow.total_tokens,
                    ProviderUsageRecordRow.usage_metadata,
                )
                .where(
                    ProviderUsageRecordRow.tenant_id == context.tenant_id,
                    ProviderUsageRecordRow.owner_user_id == context.user_id,
                    ProviderUsageRecordRow.run_id == run_id,
                )
                .order_by(ProviderUsageRecordRow.created_at.asc())
            )
        ).all()
        return [
            ProviderUsageAggregate(
                run_id=row.run_id,
                provider=row.provider,
                model=row.model,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                total_tokens=row.total_tokens,
                calls=_deserialize_calls(row.usage_metadata),
            )
            for row in rows
        ]
