from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from uuid import UUID

from dayboard.app.account_recovery_ports import (
    AccountRecoveryUnitOfWork,
    PasswordHasher,
)


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class IssuedPasswordReset:
    user_id: UUID
    recipient: str
    raw_token: str


class AccountRecoveryService:
    def __init__(
        self,
        unit_of_work: AccountRecoveryUnitOfWork,
        password_hasher: PasswordHasher,
        *,
        clock: Callable[[], datetime] = utc_now,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    ) -> None:
        self.unit_of_work = unit_of_work
        self.recovery = unit_of_work.recovery
        self.password_hasher = password_hasher
        self.clock = clock
        self.token_factory = token_factory

    async def issue_token(
        self,
        email: str,
        *,
        ttl_seconds: int,
    ) -> IssuedPasswordReset | None:
        if ttl_seconds <= 0:
            raise ValueError("Password reset TTL must be positive")
        raw_token = self.token_factory()
        if not raw_token:
            raise RuntimeError("Password reset token factory returned an empty token")
        recipient = await self.recovery.replace_active_token(
            email=email.strip().lower(),
            token_hash=token_digest(raw_token),
            expires_at=self.clock() + timedelta(seconds=ttl_seconds),
        )
        if recipient is None:
            return None
        return IssuedPasswordReset(
            user_id=recipient.user_id,
            recipient=recipient.email,
            raw_token=raw_token,
        )

    async def reset_password(self, token: str, new_password: str) -> bool:
        # Hash before taking database locks and for both valid and invalid tokens.
        new_password_hash = self.password_hasher.hash(new_password)
        return await self.recovery.consume_active_token(
            token_hash=token_digest(token),
            password_hash=new_password_hash,
            used_at=self.clock(),
        )
