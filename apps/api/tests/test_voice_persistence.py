from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import TenantContext

from dayboard.app.voice_ports import AudioInput, SpeechTranscriptionResult
from dayboard.composition.voice import build_voice_services
from dayboard.db.session import SessionLocal
from dayboard.domain.voice import VoiceTranscriptStatus


async def test_voice_processing_is_visible_during_external_provider_call(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    observed_status: VoiceTranscriptStatus | None = None

    class ObservingProvider:
        name = "observer"

        async def transcribe(self, audio, *, language=None, vocabulary=None):
            nonlocal observed_status
            del audio, vocabulary
            async with SessionLocal() as observation_session:
                visible = await build_voice_services(observation_session).transcriptions.get(
                    tenant_context, transcript_id
                )
                assert visible is not None
                observed_status = visible.status
            return SpeechTranscriptionResult(
                text="测试语音",
                provider=self.name,
                model="observer-model",
                language=language,
            )

    scope = build_voice_services(db_session)
    transcript_id: UUID
    original_create = scope.unit_of_work.transcripts.create

    async def capture_create(*args, **kwargs):
        nonlocal transcript_id
        created = await original_create(*args, **kwargs)
        transcript_id = created.id
        return created

    scope.unit_of_work.transcripts.create = capture_create  # type: ignore[method-assign]
    completed = await scope.transcriptions.transcribe(
        tenant_context,
        ObservingProvider(),
        AudioInput(content=b"audio", content_type="audio/webm"),
    )

    assert observed_status is VoiceTranscriptStatus.processing
    assert completed.status is VoiceTranscriptStatus.completed


async def test_voice_repository_transitions_fail_closed_across_owners(
    db_session: AsyncSession,
    tenant_context: TenantContext,
) -> None:
    scope = build_voice_services(db_session)
    created = await scope.unit_of_work.transcripts.create(
        tenant_context,
        filename=None,
        content_type="audio/webm",
        audio_size_bytes=5,
    )
    await scope.unit_of_work.commit()
    other_context = TenantContext(
        tenant_id=tenant_context.tenant_id,
        user_id=uuid4(),
        timezone=tenant_context.timezone,
        locale=tenant_context.locale,
    )
    result = SpeechTranscriptionResult(
        text="不应写入",
        provider="fake",
        model="fake-model",
    )

    assert await scope.unit_of_work.transcripts.get(other_context, created.id) is None
    assert (
        await scope.unit_of_work.transcripts.complete_processing(
            other_context,
            created.id,
            result,
        )
        is None
    )
    await scope.unit_of_work.rollback()

    persisted = await scope.transcriptions.get(tenant_context, created.id)
    assert persisted is not None
    assert persisted.status is VoiceTranscriptStatus.processing
