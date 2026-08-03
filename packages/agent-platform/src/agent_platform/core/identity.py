"""Trusted user context shared by application capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserContext:
    user_id: UUID
    timezone: str
    locale: str
