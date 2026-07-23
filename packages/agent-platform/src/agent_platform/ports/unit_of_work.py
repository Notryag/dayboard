"""Explicit transaction boundaries for platform use cases."""

from __future__ import annotations

from typing import Protocol

from agent_platform.ports.conversations import (
    ConversationMessageStore,
    ConversationStateStore,
    ConversationThreadStore,
)
from agent_platform.ports.idempotency import IdempotencyStore
from agent_platform.ports.runs import RunEventStore, RunStore


class TransactionBoundary(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ConversationUnitOfWork(TransactionBoundary, Protocol):
    threads: ConversationThreadStore
    messages: ConversationMessageStore
    states: ConversationStateStore


class RunUnitOfWork(TransactionBoundary, Protocol):
    runs: RunStore
    events: RunEventStore


class IdempotencyUnitOfWork(TransactionBoundary, Protocol):
    idempotency: IdempotencyStore


class PlatformUnitOfWork(
    ConversationUnitOfWork,
    RunUnitOfWork,
    IdempotencyUnitOfWork,
    Protocol,
):
    """Stores sharing one atomic transaction boundary."""
