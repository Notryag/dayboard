from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from agent_platform.core import TenantContext

from dayboard.app.reminder_ports import ReminderUnitOfWork
from dayboard.domain.reminders import (
    CALENDAR_REMINDER_DELIVERY_GRACE,
    ReminderDelivery,
    ReminderDeliveryStatus,
    ReminderInboxItem,
    ReminderProcessingResult,
    ReminderSourceSnapshot,
    ReminderSourceStatus,
    ReminderSourceType,
)


SourceKey = tuple[UUID, UUID, ReminderSourceType, UUID]


class DeliveryDisposition(StrEnum):
    deliver = "deliver"
    expire = "expire"
    cancel = "cancel"


def utc_now() -> datetime:
    return datetime.now(UTC)


def _delivery_key(delivery: ReminderDelivery) -> SourceKey:
    return (
        delivery.tenant_id,
        delivery.owner_user_id,
        delivery.source_type,
        delivery.source_id,
    )


def _source_key(source: ReminderSourceSnapshot) -> SourceKey:
    return (source.tenant_id, source.owner_user_id, source.source_type, source.source_id)


def _payload_string(delivery: ReminderDelivery, key: str) -> str | None:
    value = delivery.payload.get(key)
    return value if isinstance(value, str) else None


def _payload_occurs_at(delivery: ReminderDelivery) -> datetime | None:
    value = _payload_string(delivery, "occurs_at")
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


def delivery_disposition(
    delivery: ReminderDelivery,
    source: ReminderSourceSnapshot | None,
    *,
    now: datetime,
    calendar_delivery_grace: timedelta = CALENDAR_REMINDER_DELIVERY_GRACE,
) -> DeliveryDisposition:
    if source is None:
        return DeliveryDisposition.cancel
    if delivery.source_type is ReminderSourceType.calendar_entry:
        if source.status is not ReminderSourceStatus.scheduled:
            return DeliveryDisposition.cancel
        if source.occurs_at is None or source.occurs_at + calendar_delivery_grace < now:
            return DeliveryDisposition.expire
        return DeliveryDisposition.deliver
    return (
        DeliveryDisposition.deliver
        if source.status is ReminderSourceStatus.open
        else DeliveryDisposition.cancel
    )


class ReminderService:
    def __init__(
        self,
        unit_of_work: ReminderUnitOfWork,
        *,
        clock: Callable[[], datetime] = utc_now,
        calendar_delivery_grace: timedelta = CALENDAR_REMINDER_DELIVERY_GRACE,
    ) -> None:
        self.unit_of_work = unit_of_work
        self.deliveries = unit_of_work.deliveries
        self.sources = unit_of_work.sources
        self.clock = clock
        self.calendar_delivery_grace = calendar_delivery_grace

    async def _source_map(
        self,
        deliveries: Sequence[ReminderDelivery],
    ) -> dict[SourceKey, ReminderSourceSnapshot]:
        return {
            _source_key(source): source
            for source in await self.sources.list_for_deliveries(deliveries)
        }

    async def _locked_source_map(
        self,
        deliveries: Sequence[ReminderDelivery],
    ) -> dict[SourceKey, ReminderSourceSnapshot]:
        return {
            _source_key(source): source
            for source in await self.sources.lock_for_deliveries(deliveries)
        }

    async def list_for_user(self, context: TenantContext) -> list[ReminderDelivery]:
        return list(await self.deliveries.list_for_user(context))

    async def list_inbox(self, context: TenantContext) -> list[ReminderInboxItem]:
        deliveries = list(await self.deliveries.list_inbox_for_user(context))
        sources = await self._source_map(deliveries)
        now = self.clock()
        items: list[ReminderInboxItem] = []
        for delivery in deliveries:
            source = sources.get(_delivery_key(delivery))
            items.append(
                ReminderInboxItem(
                    **delivery.model_dump(),
                    source_status=(
                        source.status if source is not None else ReminderSourceStatus.deleted
                    ),
                    source_occurs_at=(
                        source.occurs_at
                        if source is not None and source.occurs_at is not None
                        else _payload_occurs_at(delivery) or delivery.scheduled_for
                    ),
                    source_title=(
                        source.title if source is not None else _payload_string(delivery, "title")
                    ),
                    can_retry=(
                        delivery.status is ReminderDeliveryStatus.failed
                        and delivery_disposition(
                            delivery,
                            source,
                            now=now,
                            calendar_delivery_grace=self.calendar_delivery_grace,
                        )
                        is DeliveryDisposition.deliver
                    ),
                )
            )
        return items

    async def mark_read(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> tuple[ReminderDelivery | None, bool]:
        delivery = await self.deliveries.get_for_update(context, delivery_id)
        if delivery is None:
            return None, False
        if delivery.status is not ReminderDeliveryStatus.delivered:
            return delivery, False
        if delivery.read_at is not None:
            return delivery, True
        updated = await self.deliveries.mark_read(
            context,
            delivery_id,
            read_at=self.clock(),
        )
        return updated, updated is not None

    async def retry_failed(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> tuple[ReminderDelivery | None, bool]:
        candidate = await self.deliveries.get(context, delivery_id)
        if candidate is None:
            return None, False
        if candidate.status is not ReminderDeliveryStatus.failed:
            return candidate, False
        locked_sources = await self._locked_source_map([candidate])
        delivery = await self.deliveries.get_for_update(context, delivery_id)
        if delivery is None:
            return None, False
        if delivery.status is not ReminderDeliveryStatus.failed:
            return delivery, False
        source = locked_sources.get(_delivery_key(delivery))
        now = self.clock()
        if (
            delivery_disposition(
                delivery,
                source,
                now=now,
                calendar_delivery_grace=self.calendar_delivery_grace,
            )
            is not DeliveryDisposition.deliver
        ):
            return delivery, False
        updated = await self.deliveries.retry_failed(
            context,
            delivery_id,
            retry_at=now,
        )
        return updated, updated is not None

    async def process_due_in_app(self, *, limit: int = 100) -> ReminderProcessingResult:
        now = self.clock()
        candidates = list(
            await self.deliveries.list_due_candidates(
                now=now,
                limit=limit,
                channel="in_app",
            )
        )
        locked_sources = await self._locked_source_map(candidates)
        deliveries = list(
            await self.deliveries.claim_due(
                [candidate.id for candidate in candidates],
                now=now,
                channel="in_app",
            )
        )
        result = ReminderProcessingResult(
            delivered_ids=[],
            expired_ids=[],
            cancelled_ids=[],
        )
        for delivery in deliveries:
            disposition = delivery_disposition(
                delivery,
                locked_sources.get(_delivery_key(delivery)),
                now=now,
                calendar_delivery_grace=self.calendar_delivery_grace,
            )
            if disposition is DeliveryDisposition.expire:
                if await self.deliveries.mark_expired(delivery.id):
                    result.expired_ids.append(delivery.id)
                continue
            if disposition is DeliveryDisposition.cancel:
                if await self.deliveries.mark_cancelled(delivery.id):
                    result.cancelled_ids.append(delivery.id)
                continue
            if await self.deliveries.mark_delivered(
                delivery.id,
                delivered_at=now,
                provider_message_id=f"in_app:{delivery.id}",
            ):
                result.delivered_ids.append(delivery.id)
        return result
