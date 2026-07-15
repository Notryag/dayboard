from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator
from isodate import Duration, parse_duration


class Reminder(BaseModel):
    offset: str = Field(
        description=(
            "ISO 8601 duration before the anchor. Use PT0M at the anchor, "
            "PT10M for ten minutes before, PT1H for one hour, or P1D for one day."
        )
    )
    anchor: Literal["start_time", "due_at"] = "start_time"

    @field_validator("offset", mode="before")
    @classmethod
    def normalize_short_offset(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        match = re.fullmatch(r"\s*(\d+)\s*([mhd])\s*", value, re.IGNORECASE)
        if not match:
            return value
        amount, unit = match.groups()
        return {
            "m": f"PT{amount}M",
            "h": f"PT{amount}H",
            "d": f"P{amount}D",
        }[unit.lower()]

    @model_validator(mode="after")
    def validate_offset(self) -> Reminder:
        try:
            duration = parse_duration(self.offset)
        except (TypeError, ValueError) as exc:
            raise ValueError("offset must be an ISO 8601 duration") from exc
        if isinstance(duration, Duration) or not isinstance(duration, timedelta):
            raise ValueError("offset cannot contain calendar months or years")
        if duration < timedelta(0):
            raise ValueError("offset cannot be negative")
        return self

    def as_timedelta(self) -> timedelta:
        duration = parse_duration(self.offset)
        if not isinstance(duration, timedelta):
            raise ValueError("offset cannot contain calendar months or years")
        return duration


class CalendarEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    start_time: AwareDatetime
    end_time: AwareDatetime | None = None
    timezone: str = Field(min_length=1, max_length=64)
    participants: list[str] = Field(default_factory=list)
    reminder: Reminder | None = None
    created_by_run_id: UUID | None = None
    created_operation_key: str | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> CalendarEntryCreate:
        if self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.reminder is not None and self.reminder.anchor != "start_time":
            raise ValueError("calendar reminders must use start_time")
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
    created_operation_key: str | None
    updated_by_run_id: UUID | None
    updated_operation_key: str | None
    cancelled_by_run_id: UUID | None
    cancelled_operation_key: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
