from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.api.routes import get_speech_provider
from dayboard.db.models import VoiceTranscriptRow
from dayboard.integrations.speech import Transcript, TranscriptionError


class SuccessfulSpeechProvider:
    name = "fake-cn"

    async def transcribe(self, audio, *, language=None, vocabulary=None):
        del vocabulary
        assert audio.content == b"short-audio"
        return Transcript(
            text="明天九点开会，然后提醒我整理周报",
            provider=self.name,
            model="test-model",
            language=language,
            duration_ms=2400,
            confidence=0.96,
            provider_request_id="provider-request-1",
        )


async def test_voice_upload_returns_editable_transcript_and_persists_metadata(
    api_app: FastAPI,
) -> None:
    api_app.dependency_overrides[get_speech_provider] = SuccessfulSpeechProvider
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/voice/transcriptions",
            files={"audio": ("command.webm", b"short-audio", "audio/webm")},
            data={"language": "zh"},
        )
        loaded = await client.get(
            f"/api/voice/transcriptions/{created.json()['id']}"
        )

    assert created.status_code == 201
    assert loaded.json() == created.json()
    assert created.json()["status"] == "completed"
    assert created.json()["text"] == "明天九点开会，然后提醒我整理周报"
    assert created.json()["provider"] == "fake-cn"
    assert created.json()["confidence"] == 0.96


async def test_voice_upload_rejects_unsupported_audio_before_provider_call(
    api_app: FastAPI,
) -> None:
    api_app.dependency_overrides[get_speech_provider] = SuccessfulSpeechProvider
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/voice/transcriptions",
            files={"audio": ("command.txt", b"not-audio", "text/plain")},
        )

    assert response.status_code == 415


async def test_voice_provider_failure_is_recorded_without_exposing_details(
    api_app: FastAPI,
    db_session: AsyncSession,
) -> None:
    class FailingSpeechProvider:
        name = "failing"

        async def transcribe(self, audio, *, language=None, vocabulary=None):
            del audio, language, vocabulary
            raise TranscriptionError("provider temporarily unavailable")

    api_app.dependency_overrides[get_speech_provider] = FailingSpeechProvider
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/voice/transcriptions",
            files={"audio": ("command.webm", b"short-audio", "audio/webm")},
        )

    row = await db_session.scalar(select(VoiceTranscriptRow))
    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Speech transcription failed"
    assert row is not None
    assert row.status == "failed"
    assert row.error_message == "provider temporarily unavailable"
