from __future__ import annotations

import asyncio
from uuid import UUID

from agent_platform.core import TenantContext

from dayboard.app.voice_ports import (
    AudioInput,
    SpeechToTextProvider,
    TranscriptionError,
    VoiceUnitOfWork,
)
from dayboard.domain.voice import VoiceTranscript


class VoiceTranscriptTransitionError(RuntimeError):
    """The persisted transcript could not make its expected lifecycle transition."""


class VoiceProviderFailure(RuntimeError):
    """The external speech provider failed after the failure state was persisted."""


class VoiceTranscriptionService:
    def __init__(self, unit_of_work: VoiceUnitOfWork) -> None:
        self.unit_of_work = unit_of_work
        self.transcripts = unit_of_work.transcripts

    async def _persist_failure(
        self,
        context: TenantContext,
        transcript_id: UUID,
        message: str,
    ) -> None:
        failed = await self.transcripts.fail_processing(
            context,
            transcript_id,
            message,
        )
        if failed is None:
            raise VoiceTranscriptTransitionError(
                "Voice transcript was not processing when the provider failed"
            )
        await self.unit_of_work.commit()

    async def transcribe(
        self,
        context: TenantContext,
        provider: SpeechToTextProvider,
        audio: AudioInput,
        *,
        language: str | None = None,
        vocabulary: list[str] | None = None,
    ) -> VoiceTranscript:
        try:
            processing = await self.transcripts.create(
                context,
                filename=audio.filename,
                content_type=audio.content_type,
                audio_size_bytes=len(audio.content),
            )
            # The processing record must be durable before waiting on an external provider.
            await self.unit_of_work.commit()
        except Exception:
            await self.unit_of_work.rollback()
            raise

        try:
            result = await provider.transcribe(
                audio,
                language=language,
                vocabulary=vocabulary,
            )
        except asyncio.CancelledError:
            try:
                await self._persist_failure(
                    context,
                    processing.id,
                    "Speech transcription was cancelled",
                )
            except Exception:
                await self.unit_of_work.rollback()
                raise
            raise
        except Exception as exc:
            safe_message = (
                str(exc) or "Speech transcription failed"
                if isinstance(exc, TranscriptionError)
                else "Unexpected speech provider failure"
            )
            try:
                await self._persist_failure(
                    context,
                    processing.id,
                    safe_message,
                )
            except Exception:
                await self.unit_of_work.rollback()
                raise
            raise VoiceProviderFailure("Speech transcription failed") from exc

        if result.duration_ms is None and audio.duration_ms is not None:
            result = result.model_copy(update={"duration_ms": audio.duration_ms})
        try:
            completed = await self.transcripts.complete_processing(
                context,
                processing.id,
                result,
            )
            if completed is None:
                raise VoiceTranscriptTransitionError(
                    "Voice transcript was not processing when the provider completed"
                )
            await self.unit_of_work.commit()
        except Exception:
            await self.unit_of_work.rollback()
            raise
        return completed

    async def get(
        self,
        context: TenantContext,
        transcript_id: UUID,
    ) -> VoiceTranscript | None:
        return await self.transcripts.get(context, transcript_id)
