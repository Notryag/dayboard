from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field


@dataclass(frozen=True, slots=True)
class AudioInput:
    content: bytes
    content_type: str
    filename: str | None = None


class Transcript(BaseModel):
    text: str = Field(min_length=1)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    language: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider_request_id: str | None = None


class TranscriptionError(RuntimeError):
    """A provider-safe transcription failure without credential details."""


class SpeechToTextProvider(Protocol):
    name: str

    async def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        vocabulary: list[str] | None = None,
    ) -> Transcript: ...
