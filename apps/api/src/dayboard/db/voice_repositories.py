from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext

from dayboard.app.voice_ports import SpeechTranscriptionResult
from dayboard.db.models import VoiceTranscriptRow
from dayboard.domain.voice import VoiceTranscript, VoiceTranscriptStatus


def _voice_transcript_from_row(row: VoiceTranscriptRow) -> VoiceTranscript:
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


class VoiceTranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_processing_for_update(
        self,
        context: TenantContext,
        transcript_id: UUID,
    ) -> VoiceTranscriptRow | None:
        return await self.session.scalar(
            select(VoiceTranscriptRow)
            .where(
                VoiceTranscriptRow.id == transcript_id,
                VoiceTranscriptRow.tenant_id == context.tenant_id,
                VoiceTranscriptRow.owner_user_id == context.user_id,
                VoiceTranscriptRow.status == VoiceTranscriptStatus.processing.value,
            )
            .with_for_update()
        )

    async def create(
        self,
        context: TenantContext,
        *,
        filename: str | None,
        content_type: str,
        audio_size_bytes: int,
    ) -> VoiceTranscript:
        row = VoiceTranscriptRow(
            tenant_id=context.tenant_id,
            owner_user_id=context.user_id,
            status=VoiceTranscriptStatus.processing.value,
            filename=filename,
            content_type=content_type,
            audio_size_bytes=audio_size_bytes,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return _voice_transcript_from_row(row)

    async def complete_processing(
        self,
        context: TenantContext,
        transcript_id: UUID,
        result: SpeechTranscriptionResult,
    ) -> VoiceTranscript | None:
        row = await self._get_processing_for_update(context, transcript_id)
        if row is None:
            return None
        row.status = VoiceTranscriptStatus.completed.value
        row.text = result.text
        row.provider = result.provider
        row.model = result.model
        row.language = result.language
        row.duration_ms = result.duration_ms
        row.confidence = result.confidence
        row.provider_request_id = result.provider_request_id
        row.error_message = None
        await self.session.flush()
        await self.session.refresh(row)
        return _voice_transcript_from_row(row)

    async def fail_processing(
        self,
        context: TenantContext,
        transcript_id: UUID,
        message: str,
    ) -> VoiceTranscript | None:
        row = await self._get_processing_for_update(context, transcript_id)
        if row is None:
            return None
        row.status = VoiceTranscriptStatus.failed.value
        row.error_message = message[:1000]
        await self.session.flush()
        await self.session.refresh(row)
        return _voice_transcript_from_row(row)

    async def get(
        self,
        context: TenantContext,
        transcript_id: UUID,
    ) -> VoiceTranscript | None:
        row = await self.session.scalar(
            select(VoiceTranscriptRow).where(
                VoiceTranscriptRow.id == transcript_id,
                VoiceTranscriptRow.tenant_id == context.tenant_id,
                VoiceTranscriptRow.owner_user_id == context.user_id,
            )
        )
        return _voice_transcript_from_row(row) if row is not None else None
