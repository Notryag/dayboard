from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agent_platform.core import UserContext

from dayboard.app.voice_ports import AudioInput, SpeechTranscriptionResult
from dayboard.composition.voice import build_voice_service
from dayboard.db.session import SessionLocal
from dayboard.domain.voice import VoiceTranscriptStatus


async def test_voice_processing_is_visible_during_external_provider_call(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    observed_status: VoiceTranscriptStatus | None = None

    class ObservingProvider:
        name = "observer"

        async def transcribe(self, audio, *, language=None, vocabulary=None):
            nonlocal observed_status
            del audio, vocabulary
            async with SessionLocal() as observation_session:
                visible = await build_voice_service(observation_session).get(
                    user_context, transcript_id
                )
                assert visible is not None
                observed_status = visible.status
            return SpeechTranscriptionResult(
                text="测试语音",
                provider=self.name,
                model="observer-model",
                language=language,
            )

    service = build_voice_service(db_session)
    transcript_id: UUID
    original_create = service.unit_of_work.transcripts.create

    async def capture_create(*args, **kwargs):
        nonlocal transcript_id
        created = await original_create(*args, **kwargs)
        transcript_id = created.id
        return created

    service.unit_of_work.transcripts.create = capture_create  # type: ignore[method-assign]
    completed = await service.transcribe(
        user_context,
        ObservingProvider(),
        AudioInput(content=b"audio", content_type="audio/webm"),
    )

    assert observed_status is VoiceTranscriptStatus.processing
    assert completed.status is VoiceTranscriptStatus.completed


async def test_voice_repository_transitions_fail_closed_across_owners(
    db_session: AsyncSession,
    user_context: UserContext,
) -> None:
    service = build_voice_service(db_session)
    created = await service.unit_of_work.transcripts.create(
        user_context,
        filename=None,
        content_type="audio/webm",
        audio_size_bytes=5,
    )
    await service.unit_of_work.commit()
    other_context = UserContext(
        user_id=uuid4(),
        timezone=user_context.timezone,
        locale=user_context.locale,
    )
    result = SpeechTranscriptionResult(
        text="不应写入",
        provider="fake",
        model="fake-model",
    )

    assert await service.unit_of_work.transcripts.get(other_context, created.id) is None
    assert (
        await service.unit_of_work.transcripts.complete_processing(
            other_context,
            created.id,
            result,
        )
        is None
    )
    await service.unit_of_work.rollback()

    persisted = await service.get(user_context, created.id)
    assert persisted is not None
    assert persisted.status is VoiceTranscriptStatus.processing
