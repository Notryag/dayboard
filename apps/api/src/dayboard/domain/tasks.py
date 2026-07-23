from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from dayboard.domain.calendar import Reminder


class TaskStatus(StrEnum):
    open = "open"
    completed = "completed"
    cancelled = "cancelled"


class TaskItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    due_at: AwareDatetime | None = None
    timezone: str = Field(min_length=1, max_length=64)
    reminder: Reminder | None = None
    status: TaskStatus = TaskStatus.open
    created_by_run_id: UUID | None = None
    created_operation_key: str | None = None

    @model_validator(mode="after")
    def normalize_reminder_anchor(self) -> TaskItemCreate:
        if self.reminder is not None:
            if self.due_at is None:
                raise ValueError("task reminders require due_at")
            self.reminder = self.reminder.model_copy(update={"anchor": "due_at"})
        return self


class TaskItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    due_at: AwareDatetime | None = None
    status: TaskStatus | None = None
    updated_by_run_id: UUID
    updated_operation_key: str


class TaskItem(BaseModel):
    id: UUID
    row_version: int = Field(ge=1)
    tenant_id: UUID
    owner_user_id: UUID
    title: str
    due_at: AwareDatetime | None
    timezone: str
    reminder: Reminder | None
    status: TaskStatus
    created_by_run_id: UUID | None
    created_operation_key: str | None
    updated_by_run_id: UUID | None
    updated_operation_key: str | None
    created_at: datetime
    updated_at: datetime
