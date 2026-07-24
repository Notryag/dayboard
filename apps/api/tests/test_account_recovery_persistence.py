from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.api.auth import _account_for_login, _login_credential_snapshot
from dayboard.app.account_recovery import AccountRecoveryService, token_digest
from dayboard.composition.account_recovery import build_account_recovery_services
from dayboard.db.account_recovery_uow import SqlAlchemyAccountRecoveryUnitOfWork
from dayboard.db.models import (
    PasswordResetTokenRow,
    TenantMembershipRow,
    TenantRow,
    UserCredentialRow,
    UserProfileRow,
    UserRow,
    UserSessionRow,
)
from dayboard.db.session import SessionLocal


class FastPasswordHasher:
    def hash(self, password: str) -> str:
        return f"test-hash:{password}"


async def _create_password_account(db_session: AsyncSession) -> UserRow:
    user = UserRow(
        username=f"recovery-{uuid4().hex}",
        email=f"recovery-{uuid4().hex}@example.com",
    )
    tenant = TenantRow(name="Recovery test")
    db_session.add_all([user, tenant])
    await db_session.flush()
    db_session.add_all(
        [
            UserCredentialRow(user_id=user.id, password_hash="test-hash:old-password"),
            UserProfileRow(user_id=user.id, timezone="Asia/Shanghai", locale="zh-CN"),
            TenantMembershipRow(tenant_id=tenant.id, user_id=user.id, role="owner"),
        ]
    )
    await db_session.commit()
    return user


async def _issue_reset(db_session: AsyncSession, user: UserRow) -> str:
    scope = build_account_recovery_services(db_session)
    issued = await scope.recovery.issue_token(user.email or "", ttl_seconds=900)
    assert issued is not None
    await scope.unit_of_work.commit()
    return issued.raw_token


async def test_password_reset_token_is_consumed_once_under_concurrency(
    db_session: AsyncSession,
) -> None:
    user = await _create_password_account(db_session)
    raw_token = await _issue_reset(db_session, user)

    async def attempt_reset(password: str) -> tuple[str, bool]:
        async with SessionLocal() as session:
            unit_of_work = SqlAlchemyAccountRecoveryUnitOfWork(session)
            service = AccountRecoveryService(unit_of_work, FastPasswordHasher())
            changed = await service.reset_password(raw_token, password)
            await unit_of_work.commit()
            return password, changed

    results = await asyncio.wait_for(
        asyncio.gather(attempt_reset("first-password"), attempt_reset("second-password")),
        timeout=2,
    )

    assert sorted(changed for _, changed in results) == [False, True]
    winning_password = next(password for password, changed in results if changed)
    token = await db_session.scalar(select(PasswordResetTokenRow))
    credential = await db_session.get(UserCredentialRow, user.id)
    assert token is not None and token.used_at is not None
    assert credential is not None
    await db_session.refresh(credential)
    assert credential.password_hash == f"test-hash:{winning_password}"


async def test_token_issue_and_confirm_share_user_first_lock_order(
    db_session: AsyncSession,
) -> None:
    user = await _create_password_account(db_session)
    old_token = await _issue_reset(db_session, user)

    async def confirm_old_token() -> bool:
        async with SessionLocal() as session:
            unit_of_work = SqlAlchemyAccountRecoveryUnitOfWork(session)
            service = AccountRecoveryService(unit_of_work, FastPasswordHasher())
            changed = await service.reset_password(old_token, "confirmed-password")
            await unit_of_work.commit()
            return changed

    async def issue_new_token() -> str:
        async with SessionLocal() as session:
            unit_of_work = SqlAlchemyAccountRecoveryUnitOfWork(session)
            service = AccountRecoveryService(
                unit_of_work,
                FastPasswordHasher(),
                token_factory=lambda: "replacement-token",
            )
            issued = await service.issue_token(user.email or "", ttl_seconds=900)
            assert issued is not None
            await unit_of_work.commit()
            return issued.raw_token

    confirmed, replacement_token = await asyncio.wait_for(
        asyncio.gather(confirm_old_token(), issue_new_token()),
        timeout=2,
    )

    assert replacement_token == "replacement-token"
    async with SessionLocal() as verification_session:
        tokens = list(await verification_session.scalars(select(PasswordResetTokenRow)))
        credential = await verification_session.get(UserCredentialRow, user.id)
        assert len(tokens) == 1
        assert tokens[0].token_hash == token_digest("replacement-token")
        assert tokens[0].used_at is None
        assert credential is not None
        assert credential.password_hash == (
            "test-hash:confirmed-password" if confirmed else "test-hash:old-password"
        )


async def test_account_recovery_failure_rolls_back_password_token_and_sessions(
    db_session: AsyncSession,
) -> None:
    user = await _create_password_account(db_session)
    raw_token = await _issue_reset(db_session, user)
    active_session = UserSessionRow(
        user_id=user.id,
        token_hash="b" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(active_session)
    await db_session.commit()

    async with SessionLocal() as failing_session:
        unit_of_work = SqlAlchemyAccountRecoveryUnitOfWork(failing_session)
        original_consume = unit_of_work.recovery.consume_active_token

        async def fail_after_updates(**kwargs):
            changed = await original_consume(**kwargs)
            assert changed is True
            raise RuntimeError("simulated persistence failure")

        unit_of_work.recovery.consume_active_token = fail_after_updates  # type: ignore[method-assign]
        service = AccountRecoveryService(unit_of_work, FastPasswordHasher())
        with pytest.raises(RuntimeError, match="simulated persistence failure"):
            await service.reset_password(raw_token, "new-password")
        await unit_of_work.rollback()

    async with SessionLocal() as verification_session:
        token = await verification_session.scalar(select(PasswordResetTokenRow))
        credential = await verification_session.get(UserCredentialRow, user.id)
        persisted_session = await verification_session.get(UserSessionRow, active_session.id)
        assert token is not None and token.used_at is None
        assert credential is not None
        assert credential.password_hash == "test-hash:old-password"
        assert persisted_session is not None and persisted_session.revoked_at is None


async def test_login_lookup_rejects_soft_deleted_credentials(
    db_session: AsyncSession,
) -> None:
    user = await _create_password_account(db_session)
    credential = await db_session.get(UserCredentialRow, user.id)
    assert credential is not None
    credential.deleted_at = datetime.now(UTC)
    await db_session.commit()

    async with SessionLocal() as login_session:
        assert await _login_credential_snapshot(login_session, user.email or "") is None


async def test_password_reset_invalidates_an_unlocked_login_snapshot(
    db_session: AsyncSession,
) -> None:
    user = await _create_password_account(db_session)
    raw_token = await _issue_reset(db_session, user)

    async with SessionLocal() as login_session, SessionLocal() as reset_session:
        snapshot = await _login_credential_snapshot(login_session, user.email or "")
        assert snapshot == (user.id, "test-hash:old-password")
        await login_session.rollback()

        async def reset_password() -> bool:
            unit_of_work = SqlAlchemyAccountRecoveryUnitOfWork(reset_session)
            service = AccountRecoveryService(unit_of_work, FastPasswordHasher())
            changed = await service.reset_password(raw_token, "new-password")
            await unit_of_work.commit()
            return changed

        assert await asyncio.wait_for(reset_password(), timeout=1) is True
        assert await _account_for_login(login_session, snapshot[0], snapshot[1]) is None
        await login_session.rollback()

    credential = await db_session.get(UserCredentialRow, user.id)
    assert credential is not None
    await db_session.refresh(credential)
    assert credential.password_hash == "test-hash:new-password"
