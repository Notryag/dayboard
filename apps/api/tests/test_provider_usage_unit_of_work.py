from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from agent_platform.core import TenantContext
from dayboard.app.provider_usage import ProviderUsageService
from dayboard.app.provider_usage_ports import (
    ProviderUsageAggregate,
    ProviderUsageCall,
    ProviderUsageSettlement,
)


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


class FakeUsageStore:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.aggregates: list[ProviderUsageAggregate] = []

    async def settle(self, context, aggregate):
        del context
        self.aggregates.append(aggregate)
        if self.error is not None:
            raise self.error
        return ProviderUsageSettlement(created=True)


class FakeProviderUsageUnitOfWork:
    def __init__(
        self,
        *,
        store_error: BaseException | None = None,
        commit_error: BaseException | None = None,
    ) -> None:
        self.usage = FakeUsageStore(store_error)
        self.commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.rollbacks += 1


def _service(unit_of_work: FakeProviderUsageUnitOfWork) -> ProviderUsageService:
    @asynccontextmanager
    async def factory():
        yield unit_of_work

    return ProviderUsageService(factory)


async def test_provider_usage_service_commits_successful_settlement(
    tenant_context: TenantContext,
) -> None:
    unit_of_work = FakeProviderUsageUnitOfWork()
    aggregate = _aggregate()

    settlement = await _service(unit_of_work).settle(tenant_context, aggregate)

    assert settlement.created is True
    assert unit_of_work.usage.aggregates == [aggregate]
    assert unit_of_work.commits == 1
    assert unit_of_work.rollbacks == 0


@pytest.mark.parametrize(
    ("store_error", "commit_error"),
    [
        (RuntimeError("store failed"), None),
        (None, RuntimeError("commit failed")),
        (asyncio.CancelledError(), None),
    ],
)
async def test_provider_usage_service_rolls_back_and_preserves_failures(
    tenant_context: TenantContext,
    store_error: BaseException | None,
    commit_error: BaseException | None,
) -> None:
    unit_of_work = FakeProviderUsageUnitOfWork(
        store_error=store_error,
        commit_error=commit_error,
    )
    expected_error = store_error or commit_error
    assert expected_error is not None

    with pytest.raises(type(expected_error), match=str(expected_error) or None):
        await _service(unit_of_work).settle(tenant_context, _aggregate())

    assert unit_of_work.rollbacks == 1
    assert unit_of_work.commits == (0 if store_error is not None else 1)


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
