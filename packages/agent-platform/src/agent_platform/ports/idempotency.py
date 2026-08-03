"""Persistence port for idempotent command claims."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from agent_platform.core.idempotency import IdempotencyClaim, IdempotencyRecord
from agent_platform.core.identity import UserContext


class IdempotencyStore(Protocol):
    async def get(
        self,
        context: UserContext,
        *,
        key: str,
    ) -> IdempotencyRecord | None: ...

    async def claim(
        self,
        context: UserContext,
        *,
        key: str,
        request_hash: str,
        run_id: UUID,
    ) -> IdempotencyClaim: ...

    async def delete_created_before(self, cutoff: datetime) -> int: ...
