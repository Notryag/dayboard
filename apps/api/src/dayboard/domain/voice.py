from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class VoiceTranscriptStatus(StrEnum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class VoiceTranscript(BaseModel):
    id: UUID
    status: VoiceTranscriptStatus
    filename: str | None
    content_type: str
    audio_size_bytes: int
    text: str | None
    provider: str | None
    model: str | None
    language: str | None
    duration_ms: int | None
    confidence: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
