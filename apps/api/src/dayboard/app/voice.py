from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import VoiceTranscriptRow
from dayboard.db.voice_repositories import VoiceTranscriptRepository
from dayboard.domain.voice import VoiceTranscript, VoiceTranscriptStatus
from dayboard.integrations.speech import (
    AudioInput,
    SpeechToTextProvider,
    TranscriptionError,
)


def voice_transcript_from_row(row: VoiceTranscriptRow) -> VoiceTranscript:
    return VoiceTranscript(
        id=row.id,
        status=VoiceTranscriptStatus(row.status),
        filename=row.filename,
        content_type=row.content_type,
        audio_size_bytes=row.audio_size_bytes,
        text=row.text,
        provider=row.provider,
        model=row.model,
        language=row.language,
        duration_ms=row.duration_ms,
        confidence=row.confidence,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VoiceTranscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.transcripts = VoiceTranscriptRepository(session)

    async def transcribe(
        self,
        context: TenantContext,
        provider: SpeechToTextProvider,
        audio: AudioInput,
        *,
        language: str | None = None,
        vocabulary: list[str] | None = None,
    ) -> VoiceTranscript:
        row = await self.transcripts.create(
            context,
            filename=audio.filename,
            content_type=audio.content_type,
            audio_size_bytes=len(audio.content),
        )
        await self.session.commit()
        try:
            result = await provider.transcribe(
                audio,
                language=language,
                vocabulary=vocabulary,
            )
        except Exception as exc:
            safe_message = (
                str(exc) or "Speech transcription failed"
                if isinstance(exc, TranscriptionError)
                else "Unexpected speech provider failure"
            )
            await self.transcripts.fail(row, safe_message)
            await self.session.commit()
            raise
        await self.transcripts.complete(row, result)
        await self.session.commit()
        return voice_transcript_from_row(row)

    async def get(
        self,
        context: TenantContext,
        transcript_id: UUID,
    ) -> VoiceTranscript | None:
        row = await self.transcripts.get(context, transcript_id)
        return voice_transcript_from_row(row) if row else None
