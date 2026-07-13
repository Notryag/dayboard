from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dayboard.api.routes import get_audio_metadata_probe, get_speech_provider
from dayboard.config import Settings, get_settings
from dayboard.db.models import VoiceTranscriptRow
from dayboard.integrations.audio_probe import AudioMetadata, InvalidAudioError
from dayboard.integrations.speech import Transcript, TranscriptionError


class FixedAudioProbe:
    def __init__(self, duration_ms: int = 2400) -> None:
        self.duration_ms = duration_ms

    async def inspect(self, content: bytes, *, content_type: str) -> AudioMetadata:
        assert content == b"short-audio"
        assert content_type == "audio/webm"
        return AudioMetadata(duration_ms=self.duration_ms)


class SuccessfulSpeechProvider:
    name = "fake-cn"

    async def transcribe(self, audio, *, language=None, vocabulary=None):
        del vocabulary
        assert audio.content == b"short-audio"
        assert audio.content_type == "audio/webm"
        assert audio.duration_ms == 2400
        return Transcript(
            text="明天九点开会，然后提醒我整理周报",
            provider=self.name,
            model="test-model",
            language=language,
            confidence=0.96,
            provider_request_id="provider-request-1",
        )


async def test_voice_upload_returns_editable_transcript_and_persists_metadata(
    api_app: FastAPI,
) -> None:
    api_app.dependency_overrides[get_speech_provider] = SuccessfulSpeechProvider
    api_app.dependency_overrides[get_audio_metadata_probe] = FixedAudioProbe
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/api/voice/transcriptions",
            files={
                "audio": (
                    "command.webm",
                    b"short-audio",
                    "audio/webm;codecs=opus",
                )
            },
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
    assert created.json()["duration_ms"] == 2400
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
    api_app.dependency_overrides[get_audio_metadata_probe] = FixedAudioProbe
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
    assert response.json()["error"]["code"] == "VOICE_TRANSCRIPTION_FAILED"
    assert response.json()["error"]["message"] == "Speech transcription failed"
    assert row is not None
    assert row.status == "failed"
    assert row.error_message == "provider temporarily unavailable"


async def test_voice_upload_rejects_audio_over_duration_limit(api_app: FastAPI) -> None:
    api_app.dependency_overrides[get_speech_provider] = SuccessfulSpeechProvider
    api_app.dependency_overrides[get_audio_metadata_probe] = lambda: FixedAudioProbe(6000)
    api_app.dependency_overrides[get_settings] = lambda: Settings(
        DAYBOARD_ASR_MAX_AUDIO_SECONDS=5,
        DAYBOARD_RATE_LIMIT_ENABLED=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/voice/transcriptions",
            files={"audio": ("command.webm", b"short-audio", "audio/webm")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "VOICE_TOO_LONG"
    assert response.json()["error"]["details"] == {"max_duration_seconds": 5}


async def test_voice_upload_rejects_unreadable_audio(api_app: FastAPI) -> None:
    class InvalidAudioProbe:
        async def inspect(self, content: bytes, *, content_type: str) -> AudioMetadata:
            del content, content_type
            raise InvalidAudioError("provider detail must not be returned")

    api_app.dependency_overrides[get_speech_provider] = SuccessfulSpeechProvider
    api_app.dependency_overrides[get_audio_metadata_probe] = InvalidAudioProbe

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/voice/transcriptions",
            files={"audio": ("command.webm", b"short-audio", "audio/webm")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VOICE_INVALID_AUDIO"
    assert "provider detail" not in response.text


async def test_voice_capabilities_reflect_provider_configuration(api_app: FastAPI) -> None:
    api_app.dependency_overrides[get_settings] = lambda: Settings(
        DAYBOARD_ASR_MAX_AUDIO_SECONDS=60,
        DAYBOARD_ASR_MAX_UPLOAD_BYTES=1024,
        DAYBOARD_RATE_LIMIT_ENABLED=False,
    )
    if hasattr(api_app.state, "speech_provider"):
        del api_app.state.speech_provider

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://test",
    ) as client:
        unavailable = await client.get("/api/voice/capabilities")
        api_app.state.speech_provider = SuccessfulSpeechProvider()
        available = await client.get("/api/voice/capabilities")

    del api_app.state.speech_provider
    assert unavailable.json()["available"] is False
    assert available.json()["available"] is True
    assert available.json()["max_duration_seconds"] == 60
    assert available.json()["max_upload_bytes"] == 1024
    assert "audio/webm" in available.json()["supported_content_types"]
