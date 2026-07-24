"""Storage-neutral contracts for provider usage settlement."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from agent_platform.core import TenantContext


def _validate_tokens(*values: int) -> None:
    if any(value < 0 for value in values):
        raise ValueError("Provider usage token counts cannot be negative")


@dataclass(frozen=True, slots=True)
class ProviderUsageCall:
    call_id: str
    input_tokens: int
    output_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ValueError("Provider usage call_id cannot be empty")
        _validate_tokens(self.input_tokens, self.output_tokens, self.total_tokens)


@dataclass(frozen=True, slots=True)
class ProviderUsageAggregate:
    run_id: UUID
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    calls: tuple[ProviderUsageCall, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("Provider usage provider cannot be empty")
        if not self.model.strip():
            raise ValueError("Provider usage model cannot be empty")
        _validate_tokens(self.input_tokens, self.output_tokens, self.total_tokens)


@dataclass(frozen=True, slots=True)
class ProviderUsageSettlement:
    created: bool


class ProviderUsageRunNotFound(LookupError):
    """The requested Run is not visible to the trusted tenant/owner context."""


class ProviderUsageStore(Protocol):
    async def settle(
        self,
        context: TenantContext,
        aggregate: ProviderUsageAggregate,
    ) -> ProviderUsageSettlement: ...

    async def list_for_run(
        self,
        context: TenantContext,
        run_id: UUID,
    ) -> list[ProviderUsageAggregate]: ...


class ProviderUsageUnitOfWork(Protocol):
    usage: ProviderUsageStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ProviderUsageUnitOfWorkFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[ProviderUsageUnitOfWork]: ...
