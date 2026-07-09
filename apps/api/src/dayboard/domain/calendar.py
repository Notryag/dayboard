from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Reminder(BaseModel):
    offset: str
    anchor: str = "start_time"


class CalendarEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    start_time: datetime
    end_time: datetime | None = None
    timezone: str = Field(min_length=1, max_length=64)
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = None
    created_by_run_id: UUID | None = None


class CalendarEntry(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    title: str
    start_time: datetime
    end_time: datetime | None
    timezone: str
    participants: list[str]
    reminder: Reminder | None
    created_by_run_id: UUID | None
    created_at: datetime
    updated_at: datetime
