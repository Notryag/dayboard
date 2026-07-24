"""Storage-neutral contracts for Reminder inbox and delivery use cases."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from agent_platform.core import TenantContext

from dayboard.domain.reminders import ReminderDelivery, ReminderSourceSnapshot


class ReminderDeliveryStore(Protocol):
    async def list_for_user(self, context: TenantContext) -> Sequence[ReminderDelivery]: ...

    async def list_inbox_for_user(
        self,
        context: TenantContext,
        *,
        limit: int = 100,
    ) -> Sequence[ReminderDelivery]: ...

    async def get(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> ReminderDelivery | None: ...

    async def get_for_update(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> ReminderDelivery | None: ...

    async def mark_read(
        self,
        context: TenantContext,
        delivery_id: UUID,
        *,
        read_at: datetime,
    ) -> ReminderDelivery | None: ...

    async def retry_failed(
        self,
        context: TenantContext,
        delivery_id: UUID,
        *,
        retry_at: datetime,
    ) -> ReminderDelivery | None: ...

    async def list_due_candidates(
        self,
        *,
        now: datetime,
        limit: int,
        channel: str,
    ) -> Sequence[ReminderDelivery]: ...

    async def claim_due(
        self,
        delivery_ids: Sequence[UUID],
        *,
        now: datetime,
        channel: str,
    ) -> Sequence[ReminderDelivery]: ...

    async def mark_delivered(
        self,
        delivery_id: UUID,
        *,
        delivered_at: datetime,
        provider_message_id: str,
    ) -> bool: ...

    async def mark_expired(self, delivery_id: UUID) -> bool: ...

    async def mark_cancelled(self, delivery_id: UUID) -> bool: ...


class ReminderSourceStore(Protocol):
    async def list_for_deliveries(
        self,
        deliveries: Sequence[ReminderDelivery],
    ) -> Sequence[ReminderSourceSnapshot]: ...

    async def lock_for_deliveries(
        self,
        deliveries: Sequence[ReminderDelivery],
    ) -> Sequence[ReminderSourceSnapshot]: ...


class ReminderUnitOfWork(Protocol):
    deliveries: ReminderDeliveryStore
    sources: ReminderSourceStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
