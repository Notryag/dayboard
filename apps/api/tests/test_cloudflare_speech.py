import json

import httpx
import pytest

from dayboard.app.voice_ports import AudioInput, TranscriptionError
from dayboard.integrations.speech import CloudflareSpeechProvider


async def test_cloudflare_provider_sends_base64_audio_and_normalizes_response() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"cf-ray": "cloudflare-request-1"},
            json={
                "success": True,
                "errors": [],
                "messages": [],
                "result": {
                    "text": "明天九点开会，然后提醒我整理周报",
                    "transcription_info": {"language": "zh"},
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = CloudflareSpeechProvider(
        account_id="account-1",
        api_token="test-secret",
        client=client,
    )
    transcript = await provider.transcribe(
        AudioInput(content=b"audio-bytes", content_type="audio/webm"),
        language="zh",
        vocabulary=["Dayboard", "周报"],
    )
    await client.aclose()

    assert captured["authorization"] == "Bearer test-secret"
    assert captured["path"].endswith("/accounts/account-1/ai/run/@cf/openai/whisper-large-v3-turbo")
    assert captured["body"] == {
        "audio": "YXVkaW8tYnl0ZXM=",
        "task": "transcribe",
        "vad_filter": True,
        "language": "zh",
        "initial_prompt": "Likely vocabulary: Dayboard, 周报",
    }
    assert transcript.text == "明天九点开会，然后提醒我整理周报"
    assert transcript.provider == "cloudflare"
    assert transcript.model == "@cf/openai/whisper-large-v3-turbo"
    assert transcript.language == "zh"
    assert transcript.provider_request_id == "cloudflare-request-1"


async def test_cloudflare_provider_returns_safe_error_for_provider_failure() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403,
                json={"success": False, "errors": [{"message": "test-secret"}]},
            )
        )
    )
    provider = CloudflareSpeechProvider(
        account_id="account-1",
        api_token="test-secret",
        client=client,
    )

    with pytest.raises(TranscriptionError) as exc_info:
        await provider.transcribe(AudioInput(content=b"audio", content_type="audio/wav"))

    assert str(exc_info.value) == "Cloudflare speech transcription failed"
    assert "test-secret" not in str(exc_info.value)
    await client.aclose()
