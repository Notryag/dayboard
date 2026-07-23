from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel


class ReminderSourceType(StrEnum):
    calendar_entry = "calendar_entry"
    task_item = "task_item"


class ReminderDeliveryStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    delivered = "delivered"
    failed = "failed"
    cancelled = "cancelled"


class ReminderSourceStatus(StrEnum):
    scheduled = "scheduled"
    open = "open"
    completed = "completed"
    cancelled = "cancelled"
    deleted = "deleted"


class ReminderDelivery(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    source_type: ReminderSourceType
    source_id: UUID
    channel: str
    scheduled_for: AwareDatetime
    status: ReminderDeliveryStatus
    attempt_count: int
    next_attempt_at: AwareDatetime | None
    delivered_at: AwareDatetime | None
    read_at: AwareDatetime | None
    provider_message_id: str | None
    last_error: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReminderInboxItem(ReminderDelivery):
    source_status: ReminderSourceStatus
    source_occurs_at: AwareDatetime
