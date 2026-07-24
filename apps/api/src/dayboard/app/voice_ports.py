"""Storage and provider contracts for Voice transcription use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from agent_platform.core import TenantContext

from dayboard.domain.voice import VoiceTranscript


@dataclass(frozen=True, slots=True)
class AudioInput:
    content: bytes
    content_type: str
    filename: str | None = None
    duration_ms: int | None = None


class SpeechTranscriptionResult(BaseModel):
    text: str = Field(min_length=1)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    language: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    provider_request_id: str | None = Field(default=None, max_length=240)


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
    ) -> SpeechTranscriptionResult: ...


class VoiceTranscriptStore(Protocol):
    async def create(
        self,
        context: TenantContext,
        *,
        filename: str | None,
        content_type: str,
        audio_size_bytes: int,
    ) -> VoiceTranscript: ...

    async def complete_processing(
        self,
        context: TenantContext,
        transcript_id: UUID,
        result: SpeechTranscriptionResult,
    ) -> VoiceTranscript | None: ...

    async def fail_processing(
        self,
        context: TenantContext,
        transcript_id: UUID,
        message: str,
    ) -> VoiceTranscript | None: ...

    async def get(
        self,
        context: TenantContext,
        transcript_id: UUID,
    ) -> VoiceTranscript | None: ...


class VoiceUnitOfWork(Protocol):
    transcripts: VoiceTranscriptStore

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
