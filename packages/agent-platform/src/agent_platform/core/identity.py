"""Trusted identity and tenancy context shared by application capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


TenantIsolationMode = Literal[
    "shared",
    "dedicated_schema",
    "dedicated_database",
    "dedicated_cluster",
]


@dataclass(frozen=True, slots=True)
class TenantContext:
    tenant_id: UUID
    user_id: UUID
    timezone: str
    locale: str
    isolation_mode: TenantIsolationMode = "shared"
