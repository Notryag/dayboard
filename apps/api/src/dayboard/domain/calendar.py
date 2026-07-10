from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator


class Reminder(BaseModel):
    offset: str
    anchor: str = "start_time"


class CalendarEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    start_time: AwareDatetime
    end_time: AwareDatetime | None = None
    timezone: str = Field(min_length=1, max_length=64)
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = None
    created_by_run_id: UUID | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> CalendarEntryCreate:
        if self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class CalendarEntry(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    title: str
    start_time: AwareDatetime
    end_time: AwareDatetime | None
    timezone: str
    participants: list[str]
    reminder: Reminder | None
    created_by_run_id: UUID | None
    updated_by_run_id: UUID | None
    created_at: datetime
    updated_at: datetime
