"""Persistence and security contracts for account recovery use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PasswordResetRecipient:
    user_id: UUID
    email: str


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...


class AccountRecoveryStore(Protocol):
    async def replace_active_token(
        self,
        *,
        email: str,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetRecipient | None: ...

    async def consume_active_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        used_at: datetime,
    ) -> bool: ...


class AccountRecoveryUnitOfWork(Protocol):
    recovery: AccountRecoveryStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
