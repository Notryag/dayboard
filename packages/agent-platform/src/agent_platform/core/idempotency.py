"""Persistence-neutral idempotency contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class IdempotencyRecord(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    key: str
    request_hash: str
    run_id: UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    record: IdempotencyRecord
    created: bool
