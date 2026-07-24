from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from dayboard.app.account_recovery import AccountRecoveryService, token_digest
from dayboard.app.account_recovery_ports import PasswordResetRecipient


FIXED_NOW = datetime(2026, 7, 24, 9, 0, tzinfo=UTC)
USER_ID = UUID("00000000-0000-0000-0000-000000000123")


class FakeAccountRecoveryStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.replacement: dict[str, object] | None = None
        self.consumption: dict[str, object] | None = None

    async def replace_active_token(self, *, email, token_hash, expires_at):
        self.events.append("replace_token")
        self.replacement = {
            "email": email,
            "token_hash": token_hash,
            "expires_at": expires_at,
        }
        return PasswordResetRecipient(user_id=USER_ID, email=email)

    async def consume_active_token(self, *, token_hash, password_hash, used_at):
        self.events.append("consume_token")
        self.consumption = {
            "token_hash": token_hash,
            "password_hash": password_hash,
            "used_at": used_at,
        }
        return True


class FakeAccountRecoveryUnitOfWork:
    def __init__(self, events: list[str]) -> None:
        self.recovery = FakeAccountRecoveryStore(events)
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakePasswordHasher:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def hash(self, password: str) -> str:
        self.events.append("hash_password")
        return f"hashed:{password}"


def build_service(
    events: list[str],
) -> tuple[AccountRecoveryService, FakeAccountRecoveryUnitOfWork]:
    unit_of_work = FakeAccountRecoveryUnitOfWork(events)
    return (
        AccountRecoveryService(
            unit_of_work,
            FakePasswordHasher(events),
            clock=lambda: FIXED_NOW,
            token_factory=lambda: "fixed-reset-token",
        ),
        unit_of_work,
    )


async def test_issue_token_normalizes_identity_without_committing() -> None:
    events: list[str] = []
    service, unit_of_work = build_service(events)

    issued = await service.issue_token("  USER@Example.COM ", ttl_seconds=900)

    assert issued is not None
    assert issued.user_id == USER_ID
    assert issued.recipient == "user@example.com"
    assert issued.raw_token == "fixed-reset-token"
    assert unit_of_work.recovery.replacement == {
        "email": "user@example.com",
        "token_hash": token_digest("fixed-reset-token"),
        "expires_at": FIXED_NOW + timedelta(seconds=900),
    }
    assert events == ["replace_token"]
    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 0


async def test_reset_hashes_before_store_and_leaves_transaction_to_api() -> None:
    events: list[str] = []
    service, unit_of_work = build_service(events)

    changed = await service.reset_password("raw-token", "replacement-password")

    assert changed is True
    assert events == ["hash_password", "consume_token"]
    assert unit_of_work.recovery.consumption == {
        "token_hash": token_digest("raw-token"),
        "password_hash": "hashed:replacement-password",
        "used_at": FIXED_NOW,
    }
    assert unit_of_work.commit_count == 0
    assert unit_of_work.rollback_count == 0


async def test_issue_token_rejects_non_positive_ttl_before_storage() -> None:
    events: list[str] = []
    service, _ = build_service(events)

    with pytest.raises(ValueError, match="TTL must be positive"):
        await service.issue_token("user@example.com", ttl_seconds=0)

    assert events == []
