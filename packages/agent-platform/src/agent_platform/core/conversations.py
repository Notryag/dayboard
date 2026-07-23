"""Product-neutral conversation contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from agent_platform.core.interactions import PendingInteraction


class ConversationRole(StrEnum):
    user = "user"
    assistant = "assistant"


class ConversationThread(BaseModel):
    id: UUID
    tenant_id: UUID
    owner_user_id: UUID
    title: str | None
    status: str
    summary: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    id: UUID
    thread_id: UUID
    run_id: UUID
    role: ConversationRole
    content: str
    message_metadata: dict[str, Any]
    created_at: datetime


class ConversationMessagePage(BaseModel):
    items: list[ConversationMessage]
    next_cursor: UUID | None


class ConversationState(BaseModel):
    thread_id: UUID
    interaction: PendingInteraction | None
    version: int
    expires_at: datetime | None
    updated_at: datetime
