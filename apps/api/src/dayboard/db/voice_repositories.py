from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.context import TenantContext
from dayboard.db.models import VoiceTranscriptRow
from dayboard.domain.voice import VoiceTranscriptStatus
from dayboard.integrations.speech import Transcript


class VoiceTranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        context: TenantContext,
        *,
        filename: str | None,
        content_type: str,
        audio_size_bytes: int,
    ) -> VoiceTranscriptRow:
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
        return row

    async def complete(
        self,
        row: VoiceTranscriptRow,
        transcript: Transcript,
    ) -> VoiceTranscriptRow:
        row.status = VoiceTranscriptStatus.completed.value
        row.text = transcript.text
        row.provider = transcript.provider
        row.model = transcript.model
        row.language = transcript.language
        row.duration_ms = transcript.duration_ms
        row.confidence = transcript.confidence
        row.provider_request_id = transcript.provider_request_id
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def fail(self, row: VoiceTranscriptRow, message: str) -> VoiceTranscriptRow:
        row.status = VoiceTranscriptStatus.failed.value
        row.error_message = message[:1000]
        await self.session.flush()
        await self.session.refresh(row)
        return row

    async def get(
        self,
        context: TenantContext,
        transcript_id: UUID,
    ) -> VoiceTranscriptRow | None:
        return await self.session.scalar(
            select(VoiceTranscriptRow).where(
                VoiceTranscriptRow.id == transcript_id,
                VoiceTranscriptRow.tenant_id == context.tenant_id,
                VoiceTranscriptRow.owner_user_id == context.user_id,
            )
        )
