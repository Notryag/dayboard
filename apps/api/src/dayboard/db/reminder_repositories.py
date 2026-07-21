from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import ReminderDeliveryRow
from dayboard.domain.reminders import ReminderDeliveryStatus, ReminderSourceType


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
    ) -> ReminderDeliveryRow | None:
        await self.cancel_active(
            context, source_type=source_type, source_id=source_id, channel=channel
        )
        if scheduled_for is None or payload is None:
            return None
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
        return row

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
                    ]
                ),
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .values(status=ReminderDeliveryStatus.cancelled.value)
        )

    async def list_for_user(self, context: TenantContext) -> list[ReminderDeliveryRow]:
        result = await self.session.scalars(
            select(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.tenant_id == context.tenant_id,
                ReminderDeliveryRow.owner_user_id == context.user_id,
                ReminderDeliveryRow.deleted_at.is_(None),
            )
            .order_by(ReminderDeliveryRow.scheduled_for.desc())
        )
        return list(result)

    async def get_for_user(
        self,
        context: TenantContext,
        delivery_id: UUID,
        *,
        for_update: bool = False,
    ) -> ReminderDeliveryRow | None:
        statement = select(ReminderDeliveryRow).where(
            ReminderDeliveryRow.id == delivery_id,
            ReminderDeliveryRow.tenant_id == context.tenant_id,
            ReminderDeliveryRow.owner_user_id == context.user_id,
            ReminderDeliveryRow.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def claim_due(
        self, *, now: datetime, limit: int, channel: str
    ) -> list[ReminderDeliveryRow]:
        rows = list(
            await self.session.scalars(
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
                .order_by(ReminderDeliveryRow.scheduled_for)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        for row in rows:
            row.status = ReminderDeliveryStatus.processing.value
            row.claimed_at = now
            row.attempt_count += 1
        await self.session.flush()
        return rows

    async def mark_delivered(
        self, delivery_id: UUID, *, delivered_at: datetime, provider_message_id: str
    ) -> bool:
        result = await self.session.execute(
            update(ReminderDeliveryRow)
            .where(
                ReminderDeliveryRow.id == delivery_id,
                ReminderDeliveryRow.status == ReminderDeliveryStatus.processing.value,
            )
            .values(
                status=ReminderDeliveryStatus.delivered.value,
                delivered_at=delivered_at,
                provider_message_id=provider_message_id,
                claimed_at=None,
                last_error=None,
            )
        )
        return bool(result.rowcount)
