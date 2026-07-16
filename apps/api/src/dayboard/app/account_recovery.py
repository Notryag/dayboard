from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

from pwdlib import PasswordHash
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.db.models import (
    PasswordResetTokenRow,
    UserCredentialRow,
    UserRow,
    UserSessionRow,
)


password_hash = PasswordHash.recommended()


def token_digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedPasswordReset:
    user_id: str
    recipient: str
    raw_token: str


class AccountRecoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def issue_token(
        self,
        email: str,
        *,
        ttl_seconds: int,
    ) -> IssuedPasswordReset | None:
        now = datetime.now(timezone.utc)
        user = await self.session.scalar(
            select(UserRow)
            .where(
                UserRow.email == email,
                UserRow.is_active.is_(True),
                UserRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if user is None or user.email is None:
            return None

        await self.session.execute(
            delete(PasswordResetTokenRow).where(PasswordResetTokenRow.user_id == user.id)
        )
        raw_token = secrets.token_urlsafe(32)
        self.session.add(
            PasswordResetTokenRow(
                user_id=user.id,
                token_hash=token_digest(raw_token),
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
        )
        await self.session.commit()
        return IssuedPasswordReset(
            user_id=str(user.id),
            recipient=user.email,
            raw_token=raw_token,
        )

    async def reset_password(self, token: str, new_password: str) -> bool:
        now = datetime.now(timezone.utc)
        reset_token = await self.session.scalar(
            select(PasswordResetTokenRow)
            .join(UserRow, UserRow.id == PasswordResetTokenRow.user_id)
            .where(
                PasswordResetTokenRow.token_hash == token_digest(token),
                PasswordResetTokenRow.used_at.is_(None),
                PasswordResetTokenRow.expires_at > now,
                UserRow.is_active.is_(True),
                UserRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if reset_token is None:
            return False

        credential = await self.session.scalar(
            select(UserCredentialRow)
            .where(
                UserCredentialRow.user_id == reset_token.user_id,
                UserCredentialRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if credential is None:
            return False

        credential.password_hash = password_hash.hash(new_password)
        await self.session.execute(
            update(PasswordResetTokenRow)
            .where(
                PasswordResetTokenRow.user_id == reset_token.user_id,
                PasswordResetTokenRow.used_at.is_(None),
            )
            .values(used_at=now)
        )
        await self.session.execute(
            update(UserSessionRow)
            .where(
                UserSessionRow.user_id == reset_token.user_id,
                UserSessionRow.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self.session.commit()
        return True
