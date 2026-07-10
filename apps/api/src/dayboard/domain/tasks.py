from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

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


class TaskItem(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    title: str
    due_at: AwareDatetime | None
    timezone: str
    reminder: Reminder | None
    status: TaskStatus
    created_by_run_id: UUID | None
    created_at: datetime
    updated_at: datetime
