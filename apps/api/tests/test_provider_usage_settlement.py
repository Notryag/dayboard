from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from agent_platform.core import TenantContext
from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageCall,
    ProviderUsageSettlement,
)
from dayboard.db.provider_usage_settlement import SqlAlchemyProviderUsageSettlement


def _aggregate() -> ProviderUsageAggregate:
    return ProviderUsageAggregate(
        run_id=uuid4(),
        provider="openai",
        model="openai:gpt-test",
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
        calls=(
            ProviderUsageCall(
                call_id="call-1",
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
            ),
        ),
    )


class FakeSession:
    def __init__(self, commit_error: BaseException | None = None) -> None:
        self.commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        del exc_type, exc, traceback
        return False


class FakeRepository:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.aggregates: list[ProviderUsageAggregate] = []

    async def settle(self, context, aggregate):
        del context
        self.aggregates.append(aggregate)
        if self.error is not None:
            raise self.error
        return ProviderUsageSettlement(created=True)


def _adapter(session: FakeSession) -> SqlAlchemyProviderUsageSettlement:
    return SqlAlchemyProviderUsageSettlement(lambda: FakeSessionContext(session))  # type: ignore[arg-type]


async def test_provider_usage_adapter_commits_successful_settlement(
    tenant_context: TenantContext,
    monkeypatch,
) -> None:
    session = FakeSession()
    repository = FakeRepository()
    aggregate = _aggregate()
    monkeypatch.setattr(
        "dayboard.db.provider_usage_settlement.ProviderUsageRepository",
        lambda candidate_session: repository,
    )

    settlement = await _adapter(session).settle(tenant_context, aggregate)

    assert settlement.created is True
    assert repository.aggregates == [aggregate]
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.parametrize(
    ("repository_error", "commit_error"),
    [
        (RuntimeError("repository failed"), None),
        (None, RuntimeError("commit failed")),
        (asyncio.CancelledError(), None),
    ],
)
async def test_provider_usage_adapter_rolls_back_and_preserves_failures(
    tenant_context: TenantContext,
    monkeypatch,
    repository_error: BaseException | None,
    commit_error: BaseException | None,
) -> None:
    session = FakeSession(commit_error)
    repository = FakeRepository(repository_error)
    monkeypatch.setattr(
        "dayboard.db.provider_usage_settlement.ProviderUsageRepository",
        lambda candidate_session: repository,
    )
    expected_error = repository_error or commit_error
    assert expected_error is not None

    with pytest.raises(type(expected_error), match=str(expected_error) or None):
        await _adapter(session).settle(tenant_context, _aggregate())

    assert session.rollbacks == 1
    assert session.commits == (0 if repository_error is not None else 1)


@pytest.mark.parametrize(
    "aggregate",
    [
        lambda: ProviderUsageCall("call-1", -1, 0, 0),
        lambda: ProviderUsageAggregate(uuid4(), "", "model", 0, 0, 0),
        lambda: ProviderUsageAggregate(uuid4(), "provider", "", 0, 0, 0),
    ],
)
def test_provider_usage_contract_rejects_invalid_values(aggregate) -> None:
    with pytest.raises(ValueError):
        aggregate()
