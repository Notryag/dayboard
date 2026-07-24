from dayboard.app.voice_ports import AudioInput, SpeechTranscriptionResult
from dayboard.integrations.speech import SpeechProviderRegistry


class FakeSpeechProvider:
    name = "fake"

    async def transcribe(self, audio, *, language=None, vocabulary=None):
        del audio, vocabulary
        return SpeechTranscriptionResult(
            text="明天九点开会，然后提醒我整理周报",
            provider=self.name,
            model="deterministic-test",
            language=language,
        )


async def test_speech_provider_registry_keeps_provider_contract_replaceable() -> None:
    registry = SpeechProviderRegistry()
    registry.register("fake", FakeSpeechProvider)

    provider = registry.create("FAKE")
    transcript = await provider.transcribe(
        AudioInput(content=b"audio", content_type="audio/webm"),
        language="zh",
        vocabulary=["Dayboard"],
    )

    assert registry.names == ("fake",)
    assert transcript.text == "明天九点开会，然后提醒我整理周报"
    assert transcript.provider == "fake"
    assert transcript.language == "zh"


def test_speech_provider_registry_rejects_unknown_and_duplicate_providers() -> None:
    registry = SpeechProviderRegistry()
    registry.register("fake", FakeSpeechProvider)

    try:
        registry.register("FAKE", FakeSpeechProvider)
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("Duplicate provider registration must fail")

    try:
        registry.create("volcengine")
    except LookupError as exc:
        assert "available: fake" in str(exc)
    else:
        raise AssertionError("Unknown provider lookup must fail")
