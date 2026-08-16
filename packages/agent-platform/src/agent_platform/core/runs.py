"""Product-neutral persisted Run contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from agent_platform.core.events import EventExtensionEnvelope


class AgentRunStatus(StrEnum):
    queued = "queued"
    running = "running"
    needs_clarification = "needs_clarification"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentRunEventCategory(StrEnum):
    lifecycle = "lifecycle"
    trace = "trace"
    outputs = "outputs"
    message = "message"
    model = "model"
    tool = "tool"
    subagent = "subagent"
    middleware = "middleware"
    context = "context"
    workspace = "workspace"
    clarification = "clarification"
    error = "error"


class AgentRun(BaseModel):
    id: UUID
    user_id: UUID
    thread_id: UUID
    status: AgentRunStatus
    model_name: str | None = None
    error: str | None = None
    message_count: int = 0
    first_human_message: str | None = None
    last_ai_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentRunEvent(BaseModel):
    id: UUID
    thread_id: UUID
    run_id: UUID
    seq: int
    event_type: str = Field(min_length=1, max_length=80)
    category: AgentRunEventCategory
    content: str | None
    extension: EventExtensionEnvelope | None = None
    created_at: datetime
