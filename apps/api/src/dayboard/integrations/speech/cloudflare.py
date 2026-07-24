from __future__ import annotations

import base64
from typing import Any

import httpx

from dayboard.app.voice_ports import (
    AudioInput,
    SpeechTranscriptionResult,
    TranscriptionError,
)


class CloudflareSpeechProvider:
    name = "cloudflare"

    def __init__(
        self,
        *,
        account_id: str,
        api_token: str,
        model: str = "@cf/openai/whisper-large-v3-turbo",
        base_url: str = "https://api.cloudflare.com/client/v4",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not account_id.strip():
            raise ValueError("Cloudflare account id is required")
        if not api_token:
            raise ValueError("Cloudflare API token is required")
        if not model.strip():
            raise ValueError("Cloudflare ASR model is required")
        self.account_id = account_id.strip()
        self.api_token = api_token
        self.model = model.strip().lstrip("/")
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=120)
        self._owns_client = client is None

    async def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        vocabulary: list[str] | None = None,
    ) -> SpeechTranscriptionResult:
        payload: dict[str, Any] = {
            "audio": base64.b64encode(audio.content).decode("ascii"),
            "task": "transcribe",
            "vad_filter": True,
        }
        if language:
            payload["language"] = language
        prompt = _vocabulary_prompt(vocabulary)
        if prompt:
            payload["initial_prompt"] = prompt

        try:
            response = await self.client.post(
                f"{self.base_url}/accounts/{self.account_id}/ai/run/{self.model}",
                headers={"Authorization": f"Bearer {self.api_token}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            result = _extract_result(body)
            text = result["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Cloudflare response did not contain transcript text")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise TranscriptionError("Cloudflare speech transcription failed") from exc

        request_id = response.headers.get("cf-ray") or response.headers.get("x-request-id")
        return SpeechTranscriptionResult(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            language=_result_language(result) or language,
            provider_request_id=request_id,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


def _extract_result(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or body.get("success") is False:
        raise ValueError("Cloudflare request was not successful")
    result = body.get("result")
    if not isinstance(result, dict):
        raise ValueError("Cloudflare response did not contain a result")
    return result


def _result_language(result: dict[str, Any]) -> str | None:
    info = result.get("transcription_info")
    if not isinstance(info, dict):
        return None
    language = info.get("language")
    return language if isinstance(language, str) and language else None


def _vocabulary_prompt(vocabulary: list[str] | None) -> str | None:
    if not vocabulary:
        return None
    terms = [term.strip() for term in vocabulary if term.strip()][:50]
    if not terms:
        return None
    return ("Likely vocabulary: " + ", ".join(terms))[:1000]
