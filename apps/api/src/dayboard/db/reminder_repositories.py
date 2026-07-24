from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext

from dayboard.db.models import CalendarEntryRow, ReminderDeliveryRow, TaskItemRow
from dayboard.domain.reminders import (
    ReminderDelivery,
    ReminderDeliveryStatus,
    ReminderSourceSnapshot,
    ReminderSourceStatus,
    ReminderSourceType,
)


def reminder_delivery_from_row(row: ReminderDeliveryRow) -> ReminderDelivery:
    return ReminderDelivery.model_validate(row, from_attributes=True)


class ReminderDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_pending(
        self,
        context: TenantContext,
        *,
        source_type: ReminderSourceType,
        source_id: UUID,
        scheduled_for: datetime | None,
        payload: dict[str, object] | None = None,
        channel: str = "in_app",
    ) -> None:
        await self.cancel_active(
            context,
            source_type=source_type,
            source_id=source_id,
            channel=channel,
        )
        if scheduled_for is None or payload is None:
            return
        row = ReminderDeliveryRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            source_type=source_type.value,
            source_id=source_id,
            channel=channel,
            scheduled_for=scheduled_for,
            status=ReminderDeliveryStatus.pending.value,
            payload=payload,
        )
        self.session.add(row)
        await self.session.flush()

    async def cancel_active(
        self,
        context: TenantContext,
        *,
        source_type: ReminderSourceType,
        source_id: UUID,
        channel: str = "in_app",
    ) -> None:
        await self.session.execute(
            update(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.tenant_id == context.tenant_id,
                ReminderDeliveryRow.owner_user_id == context.user_id,
                ReminderDeliveryRow.source_type == source_type.value,
                ReminderDeliveryRow.source_id == source_id,
                ReminderDeliveryRow.channel == channel,
                ReminderDeliveryRow.status.in_(
                    [
                        ReminderDeliveryStatus.pending.value,
                        ReminderDeliveryStatus.processing.value,
                        ReminderDeliveryStatus.failed.value,
                    ]
                ),
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .values(
                status=ReminderDeliveryStatus.cancelled.value,
                claimed_at=None,
            )
        )

    async def list_for_user(self, context: TenantContext) -> list[ReminderDelivery]:
        rows = await self.session.scalars(
            select(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.tenant_id == context.tenant_id,
                ReminderDeliveryRow.owner_user_id == context.user_id,
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .order_by(ReminderDeliveryRow.scheduled_for.desc())
        )
        return [reminder_delivery_from_row(row) for row in rows]

    async def list_inbox_for_user(
        self,
        context: TenantContext,
        *,
        limit: int = 100,
    ) -> list[ReminderDelivery]:
        rows = await self.session.scalars(
            select(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.tenant_id == context.tenant_id,
                ReminderDeliveryRow.owner_user_id == context.user_id,
                ReminderDeliveryRow.status.in_(
                    [
                        ReminderDeliveryStatus.delivered.value,
                        ReminderDeliveryStatus.failed.value,
                    ]
                ),
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .order_by(ReminderDeliveryRow.scheduled_for.desc(), ReminderDeliveryRow.id.desc())
            .limit(limit)
        )
        return [reminder_delivery_from_row(row) for row in rows]

    async def get_for_update(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> ReminderDelivery | None:
        return await self._get(
            context,
            delivery_id,
            for_update=True,
        )

    async def get(
        self,
        context: TenantContext,
        delivery_id: UUID,
    ) -> ReminderDelivery | None:
        return await self._get(context, delivery_id, for_update=False)

    async def _get(
        self,
        context: TenantContext,
        delivery_id: UUID,
        *,
        for_update: bool,
    ) -> ReminderDelivery | None:
        statement = select(ReminderDeliveryRow).where(
            ReminderDeliveryRow.id == delivery_id,
            ReminderDeliveryRow.tenant_id == context.tenant_id,
            ReminderDeliveryRow.owner_user_id == context.user_id,
            ReminderDeliveryRow.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        row = await self.session.scalar(statement)
        return reminder_delivery_from_row(row) if row else None

    async def mark_read(
        self,
        context: TenantContext,
        delivery_id: UUID,
        *,
        read_at: datetime,
    ) -> ReminderDelivery | None:
        row = await self.session.scalar(
            update(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.id == delivery_id,
                ReminderDeliveryRow.tenant_id == context.tenant_id,
                ReminderDeliveryRow.owner_user_id == context.user_id,
                ReminderDeliveryRow.status == ReminderDeliveryStatus.delivered.value,
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .values(read_at=read_at)
            .returning(ReminderDeliveryRow)
        )
        return reminder_delivery_from_row(row) if row else None

    async def retry_failed(
        self,
        context: TenantContext,
        delivery_id: UUID,
        *,
        retry_at: datetime,
    ) -> ReminderDelivery | None:
        row = await self.session.scalar(
            update(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.id == delivery_id,
                ReminderDeliveryRow.tenant_id == context.tenant_id,
                ReminderDeliveryRow.owner_user_id == context.user_id,
                ReminderDeliveryRow.status == ReminderDeliveryStatus.failed.value,
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .values(
                status=ReminderDeliveryStatus.pending.value,
                next_attempt_at=retry_at,
                claimed_at=None,
                delivered_at=None,
                read_at=None,
                provider_message_id=None,
                last_error=None,
            )
            .returning(ReminderDeliveryRow)
        )
        return reminder_delivery_from_row(row) if row else None

    async def list_due_candidates(
        self,
        *,
        now: datetime,
        limit: int,
        channel: str,
    ) -> list[ReminderDelivery]:
        rows = await self.session.scalars(
            select(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.status == ReminderDeliveryStatus.pending.value,
                ReminderDeliveryRow.channel == channel,
                ReminderDeliveryRow.scheduled_for <= now,
                or_(
                    ReminderDeliveryRow.next_attempt_at.is_(None),
                    ReminderDeliveryRow.next_attempt_at <= now,
                ),
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .order_by(ReminderDeliveryRow.scheduled_for, ReminderDeliveryRow.id)
            .limit(limit)
        )
        return [reminder_delivery_from_row(row) for row in rows]

    async def claim_due(
        self,
        delivery_ids: Sequence[UUID],
        *,
        now: datetime,
        channel: str,
    ) -> list[ReminderDelivery]:
        if not delivery_ids:
            return []
        rows = list(
            await self.session.scalars(
                select(ReminderDeliveryRow)
                .where(
                    ReminderDeliveryRow.id.in_(delivery_ids),
                    ReminderDeliveryRow.status == ReminderDeliveryStatus.pending.value,
                    ReminderDeliveryRow.channel == channel,
                    ReminderDeliveryRow.scheduled_for <= now,
                    or_(
                        ReminderDeliveryRow.next_attempt_at.is_(None),
                        ReminderDeliveryRow.next_attempt_at <= now,
                    ),
                    ReminderDeliveryRow.deleted_at.is_(None),
                )
                .order_by(ReminderDeliveryRow.scheduled_for, ReminderDeliveryRow.id)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.status = ReminderDeliveryStatus.processing.value
            row.claimed_at = now
            row.attempt_count += 1
            row.updated_at = now
        await self.session.flush()
        return [reminder_delivery_from_row(row) for row in rows]

    async def mark_delivered(
        self,
        delivery_id: UUID,
        *,
        delivered_at: datetime,
        provider_message_id: str,
    ) -> bool:
        updated_id = await self.session.scalar(
            update(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.id == delivery_id,
                ReminderDeliveryRow.status == ReminderDeliveryStatus.processing.value,
            )
            .values(
                status=ReminderDeliveryStatus.delivered.value,
                delivered_at=delivered_at,
                next_attempt_at=None,
                provider_message_id=provider_message_id,
                claimed_at=None,
                last_error=None,
            )
            .returning(ReminderDeliveryRow.id)
        )
        return updated_id is not None

    async def _mark_processing_terminal(
        self,
        delivery_id: UUID,
        status: ReminderDeliveryStatus,
    ) -> bool:
        updated_id = await self.session.scalar(
            update(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.id == delivery_id,
                ReminderDeliveryRow.status == ReminderDeliveryStatus.processing.value,
            )
            .values(status=status.value, claimed_at=None, next_attempt_at=None)
            .returning(ReminderDeliveryRow.id)
        )
        return updated_id is not None

    async def mark_expired(self, delivery_id: UUID) -> bool:
        return await self._mark_processing_terminal(
            delivery_id,
            ReminderDeliveryStatus.expired,
        )

    async def mark_cancelled(self, delivery_id: UUID) -> bool:
        return await self._mark_processing_terminal(
            delivery_id,
            ReminderDeliveryStatus.cancelled,
        )


class ReminderSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_deliveries(
        self,
        deliveries: Sequence[ReminderDelivery],
    ) -> list[ReminderSourceSnapshot]:
        return await self._list_for_deliveries(deliveries, for_update=False)

    async def lock_for_deliveries(
        self,
        deliveries: Sequence[ReminderDelivery],
    ) -> list[ReminderSourceSnapshot]:
        return await self._list_for_deliveries(deliveries, for_update=True)

    async def _list_for_deliveries(
        self,
        deliveries: Sequence[ReminderDelivery],
        *,
        for_update: bool,
    ) -> list[ReminderSourceSnapshot]:
        calendar_keys = sorted(
            {
                (delivery.tenant_id, delivery.owner_user_id, delivery.source_id)
                for delivery in deliveries
                if delivery.source_type is ReminderSourceType.calendar_entry
            },
            key=lambda key: tuple(str(value) for value in key),
        )
        task_keys = sorted(
            {
                (delivery.tenant_id, delivery.owner_user_id, delivery.source_id)
                for delivery in deliveries
                if delivery.source_type is ReminderSourceType.task_item
            },
            key=lambda key: tuple(str(value) for value in key),
        )
        calendar_statement = (
            select(CalendarEntryRow)
            .where(
                tuple_(
                    CalendarEntryRow.tenant_id,
                    CalendarEntryRow.owner_user_id,
                    CalendarEntryRow.id,
                ).in_(calendar_keys)
            )
            .order_by(
                CalendarEntryRow.tenant_id,
                CalendarEntryRow.owner_user_id,
                CalendarEntryRow.id,
            )
        )
        task_statement = (
            select(TaskItemRow)
            .where(
                tuple_(
                    TaskItemRow.tenant_id,
                    TaskItemRow.owner_user_id,
                    TaskItemRow.id,
                ).in_(task_keys)
            )
            .order_by(
                TaskItemRow.tenant_id,
                TaskItemRow.owner_user_id,
                TaskItemRow.id,
            )
        )
        if for_update:
            calendar_statement = calendar_statement.with_for_update()
            task_statement = task_statement.with_for_update()
        calendar_rows = (
            list(await self.session.scalars(calendar_statement)) if calendar_keys else []
        )
        task_rows = list(await self.session.scalars(task_statement)) if task_keys else []
        snapshots = [
            ReminderSourceSnapshot(
                tenant_id=row.tenant_id,
                owner_user_id=row.owner_user_id,
                source_type=ReminderSourceType.calendar_entry,
                source_id=row.id,
                title=row.title,
                status=(
                    ReminderSourceStatus.cancelled
                    if row.deleted_at is not None
                    else ReminderSourceStatus.completed
                    if row.completed_at is not None
                    else ReminderSourceStatus.scheduled
                ),
                occurs_at=row.start_time,
            )
            for row in calendar_rows
        ]
        snapshots.extend(
            ReminderSourceSnapshot(
                tenant_id=row.tenant_id,
                owner_user_id=row.owner_user_id,
                source_type=ReminderSourceType.task_item,
                source_id=row.id,
                title=row.title,
                status=(
                    ReminderSourceStatus.deleted
                    if row.deleted_at is not None
                    else ReminderSourceStatus(row.status)
                ),
                occurs_at=row.due_at,
            )
            for row in task_rows
        )
        return snapshots
