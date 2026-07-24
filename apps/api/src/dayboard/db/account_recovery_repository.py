from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.app.account_recovery_ports import PasswordResetRecipient
from dayboard.db.models import (
    PasswordResetTokenRow,
    UserCredentialRow,
    UserRow,
    UserSessionRow,
)


class AccountRecoveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_active_token(
        self,
        *,
        email: str,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetRecipient | None:
        account = (
            await self.session.execute(
                select(UserRow.id, UserRow.email)
                .where(
                    UserRow.email == email,
                    UserRow.is_active.is_(True),
                    UserRow.deleted_at.is_(None),
                )
                .with_for_update(of=UserRow)
            )
        ).one_or_none()
        if account is None or account.email is None:
            return None

        await self.session.execute(
            delete(PasswordResetTokenRow).where(PasswordResetTokenRow.user_id == account.id)
        )
        self.session.add(
            PasswordResetTokenRow(
                user_id=account.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        await self.session.flush()
        return PasswordResetRecipient(user_id=account.id, email=account.email)

    async def consume_active_token(
        self,
        *,
        token_hash: str,
        password_hash: str,
        used_at: datetime,
    ) -> bool:
        candidate_user_id = await self.session.scalar(
            select(PasswordResetTokenRow.user_id).where(
                PasswordResetTokenRow.token_hash == token_hash,
                PasswordResetTokenRow.used_at.is_(None),
                PasswordResetTokenRow.expires_at > used_at,
            )
        )
        if candidate_user_id is None:
            return False

        user_id = await self.session.scalar(
            select(UserRow.id)
            .where(
                UserRow.id == candidate_user_id,
                UserRow.is_active.is_(True),
                UserRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if user_id is None:
            return False

        active_token_user_id = await self.session.scalar(
            select(PasswordResetTokenRow.user_id)
            .where(
                PasswordResetTokenRow.token_hash == token_hash,
                PasswordResetTokenRow.user_id == user_id,
                PasswordResetTokenRow.used_at.is_(None),
                PasswordResetTokenRow.expires_at > used_at,
            )
            .with_for_update()
        )
        if active_token_user_id is None:
            return False

        credential = await self.session.scalar(
            select(UserCredentialRow)
            .where(
                UserCredentialRow.user_id == user_id,
                UserCredentialRow.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if credential is None:
            return False

        credential.password_hash = password_hash
        await self.session.execute(
            update(PasswordResetTokenRow)
            .where(
                PasswordResetTokenRow.user_id == user_id,
                PasswordResetTokenRow.used_at.is_(None),
            )
            .values(used_at=used_at)
        )
        await self.session.execute(
            update(UserSessionRow)
            .where(
                UserSessionRow.user_id == user_id,
                UserSessionRow.revoked_at.is_(None),
            )
            .values(revoked_at=used_at)
        )
        await self.session.flush()
        return True
