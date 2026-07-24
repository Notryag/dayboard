from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_platform.core import TenantContext

from dayboard.app.voice import (
    VoiceProviderFailure,
    VoiceTranscriptTransitionError,
    VoiceTranscriptionService,
)
from dayboard.app.voice_ports import (
    AudioInput,
    SpeechTranscriptionResult,
    TranscriptionError,
)
from dayboard.domain.voice import VoiceTranscript, VoiceTranscriptStatus


class FakeVoiceTranscriptStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.transcript: VoiceTranscript | None = None

    async def create(
        self,
        context,
        *,
        filename,
        content_type,
        audio_size_bytes,
    ) -> VoiceTranscript:
        del context
        self.events.append("create")
        now = datetime.now(UTC)
        self.transcript = VoiceTranscript(
            id=uuid4(),
            status=VoiceTranscriptStatus.processing,
            filename=filename,
            content_type=content_type,
            audio_size_bytes=audio_size_bytes,
            text=None,
            provider=None,
            model=None,
            language=None,
            duration_ms=None,
            confidence=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        return self.transcript

    async def complete_processing(self, context, transcript_id, result):
        del context
        self.events.append("complete")
        if (
            self.transcript is None
            or self.transcript.id != transcript_id
            or self.transcript.status is not VoiceTranscriptStatus.processing
        ):
            return None
        self.transcript = self.transcript.model_copy(
            update={
                "status": VoiceTranscriptStatus.completed,
                "text": result.text,
                "provider": result.provider,
                "model": result.model,
                "language": result.language,
                "duration_ms": result.duration_ms,
                "confidence": result.confidence,
                "updated_at": datetime.now(UTC),
            }
        )
        return self.transcript

    async def fail_processing(self, context, transcript_id, message):
        del context
        self.events.append("fail")
        if (
            self.transcript is None
            or self.transcript.id != transcript_id
            or self.transcript.status is not VoiceTranscriptStatus.processing
        ):
            return None
        self.transcript = self.transcript.model_copy(
            update={
                "status": VoiceTranscriptStatus.failed,
                "error_message": message,
                "updated_at": datetime.now(UTC),
            }
        )
        return self.transcript

    async def get(self, context, transcript_id):
        del context
        return self.transcript if self.transcript and self.transcript.id == transcript_id else None


class FakeVoiceUnitOfWork:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.transcripts = FakeVoiceTranscriptStore(events)
        self.commit_count = 0
        self.rollback_count = 0

    async def commit(self) -> None:
        self.events.append("commit")
        self.commit_count += 1

    async def rollback(self) -> None:
        self.events.append("rollback")
        self.rollback_count += 1


class PersistenceFailure(RuntimeError):
    pass


class SuccessfulProvider:
    name = "fake"

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def transcribe(self, audio, *, language=None, vocabulary=None):
        del vocabulary
        assert self.events == ["create", "commit"]
        self.events.append("provider")
        return SpeechTranscriptionResult(
            text="明天上午开会",
            provider=self.name,
            model="fake-model",
            language=language,
            duration_ms=audio.duration_ms,
        )


async def test_voice_service_commits_processing_before_provider_and_terminal_state(
    tenant_context: TenantContext,
) -> None:
    events: list[str] = []
    unit_of_work = FakeVoiceUnitOfWork(events)

    transcript = await VoiceTranscriptionService(unit_of_work).transcribe(
        tenant_context,
        SuccessfulProvider(events),
        AudioInput(
            content=b"audio",
            content_type="audio/webm",
            filename="command.webm",
            duration_ms=2400,
        ),
        language="zh",
    )

    assert events == ["create", "commit", "provider", "complete", "commit"]
    assert unit_of_work.commit_count == 2
    assert unit_of_work.rollback_count == 0
    assert transcript.status is VoiceTranscriptStatus.completed
    assert transcript.text == "明天上午开会"


async def test_voice_service_persists_safe_provider_failure(
    tenant_context: TenantContext,
) -> None:
    events: list[str] = []
    unit_of_work = FakeVoiceUnitOfWork(events)

    class FailingProvider:
        name = "fake"

        async def transcribe(self, audio, *, language=None, vocabulary=None):
            del audio, language, vocabulary
            events.append("provider")
            raise TranscriptionError("provider temporarily unavailable")

    with pytest.raises(VoiceProviderFailure) as exc_info:
        await VoiceTranscriptionService(unit_of_work).transcribe(
            tenant_context,
            FailingProvider(),
            AudioInput(content=b"audio", content_type="audio/webm"),
        )

    assert isinstance(exc_info.value.__cause__, TranscriptionError)
    assert events == ["create", "commit", "provider", "fail", "commit"]
    assert unit_of_work.transcripts.transcript is not None
    assert unit_of_work.transcripts.transcript.status is VoiceTranscriptStatus.failed
    assert unit_of_work.transcripts.transcript.error_message == "provider temporarily unavailable"


async def test_voice_service_persists_cancellation_without_converting_it_to_provider_failure(
    tenant_context: TenantContext,
) -> None:
    events: list[str] = []
    unit_of_work = FakeVoiceUnitOfWork(events)

    class CancelledProvider:
        name = "fake"

        async def transcribe(self, audio, *, language=None, vocabulary=None):
            del audio, language, vocabulary
            events.append("provider")
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await VoiceTranscriptionService(unit_of_work).transcribe(
            tenant_context,
            CancelledProvider(),
            AudioInput(content=b"audio", content_type="audio/webm"),
        )

    assert events == ["create", "commit", "provider", "fail", "commit"]
    assert unit_of_work.transcripts.transcript is not None
    assert unit_of_work.transcripts.transcript.status is VoiceTranscriptStatus.failed
    assert unit_of_work.transcripts.transcript.error_message == (
        "Speech transcription was cancelled"
    )


async def test_voice_transition_failure_is_not_mapped_to_provider_failure(
    tenant_context: TenantContext,
) -> None:
    events: list[str] = []
    unit_of_work = FakeVoiceUnitOfWork(events)

    async def reject_completion(context, transcript_id, result):
        del context, transcript_id, result
        events.append("complete")
        return None

    unit_of_work.transcripts.complete_processing = reject_completion  # type: ignore[method-assign]
    with pytest.raises(VoiceTranscriptTransitionError):
        await VoiceTranscriptionService(unit_of_work).transcribe(
            tenant_context,
            SuccessfulProvider(events),
            AudioInput(content=b"audio", content_type="audio/webm"),
        )

    assert events == ["create", "commit", "provider", "complete", "rollback"]


async def test_voice_terminal_commit_failure_is_not_mapped_to_provider_failure(
    tenant_context: TenantContext,
) -> None:
    events: list[str] = []
    unit_of_work = FakeVoiceUnitOfWork(events)
    original_commit = unit_of_work.commit

    async def fail_terminal_commit() -> None:
        if unit_of_work.commit_count == 1:
            events.append("commit_failed")
            raise PersistenceFailure("database unavailable")
        await original_commit()

    unit_of_work.commit = fail_terminal_commit  # type: ignore[method-assign]
    with pytest.raises(PersistenceFailure, match="database unavailable"):
        await VoiceTranscriptionService(unit_of_work).transcribe(
            tenant_context,
            SuccessfulProvider(events),
            AudioInput(content=b"audio", content_type="audio/webm"),
        )

    assert events == [
        "create",
        "commit",
        "provider",
        "complete",
        "commit_failed",
        "rollback",
    ]
