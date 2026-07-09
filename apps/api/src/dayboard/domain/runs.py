from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRunStatus(StrEnum):
    queued = "queued"
    running = "running"
    needs_clarification = "needs_clarification"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentRunEventCategory(StrEnum):
    lifecycle = "lifecycle"
    tool = "tool"
    clarification = "clarification"
    error = "error"


class AgentRun(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    thread_id: UUID
    status: AgentRunStatus
    input_message: str
    result_message: str | None
    created_at: datetime
    updated_at: datetime


class AgentRunEvent(BaseModel):
    id: UUID
    tenant_id: UUID
    run_id: UUID
    seq: int
    event_type: str = Field(min_length=1, max_length=80)
    category: AgentRunEventCategory
    content: str | None
    event_metadata: dict[str, Any]
    created_at: datetime
