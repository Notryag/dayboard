import json

import httpx

from dayboard.app.voice_ports import AudioInput, TranscriptionError
from dayboard.integrations.speech import AliyunSpeechProvider


async def test_aliyun_provider_sends_base64_audio_and_normalizes_response() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "aliyun-request-1"},
            json={
                "output": {
                    "choices": [
                        {"message": {"content": [{"text": "明天九点开会，然后提醒我整理周报"}]}}
                    ]
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AliyunSpeechProvider(api_key="test-secret", client=client)
    transcript = await provider.transcribe(
        AudioInput(content=b"audio-bytes", content_type="audio/webm"),
        language="zh",
    )
    await client.aclose()

    assert captured["authorization"] == "Bearer test-secret"
    audio = captured["body"]["input"]["messages"][0]["content"][0]["audio"]
    assert audio == "data:audio/webm;base64,YXVkaW8tYnl0ZXM="
    assert captured["body"]["parameters"]["asr_options"]["language"] == "zh"
    assert transcript.text == "明天九点开会，然后提醒我整理周报"
    assert transcript.provider == "aliyun"
    assert transcript.provider_request_id == "aliyun-request-1"


async def test_aliyun_provider_returns_safe_error_for_invalid_response() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"output": {}}))
    )
    provider = AliyunSpeechProvider(api_key="test-secret", client=client)

    try:
        await provider.transcribe(AudioInput(content=b"audio", content_type="audio/wav"))
    except TranscriptionError as exc:
        assert str(exc) == "Aliyun speech transcription failed"
        assert "test-secret" not in str(exc)
    else:
        raise AssertionError("Invalid provider response must fail")
    await client.aclose()
