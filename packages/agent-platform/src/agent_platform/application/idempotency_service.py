"""Idempotency validation independent of persistence implementation."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from uuid import UUID

from agent_platform.core.errors import IdempotencyConflictError
from agent_platform.core.idempotency import IdempotencyClaim
from agent_platform.core.identity import TenantContext
from agent_platform.ports.unit_of_work import IdempotencyUnitOfWork


class IdempotencyService:
    def __init__(self, unit_of_work: IdempotencyUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.store = unit_of_work.idempotency

    async def claim(
        self,
        context: TenantContext,
        *,
        key: str,
        request_identity: str,
        run_id: UUID,
    ) -> IdempotencyClaim:
        request_hash = sha256(request_identity.encode("utf-8")).hexdigest()
        claim = await self.store.claim(
            context,
            key=key,
            request_hash=request_hash,
            run_id=run_id,
        )
        if not claim.created and claim.record.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Idempotency-Key was already used for a different request"
            )
        return claim

    async def delete_created_before(self, cutoff: datetime) -> int:
        try:
            deleted = await self.store.delete_created_before(cutoff)
            await self.unit_of_work.commit()
            return deleted
        except BaseException:
            await self.unit_of_work.rollback()
            raise
