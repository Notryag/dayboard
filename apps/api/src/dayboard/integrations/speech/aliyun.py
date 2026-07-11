from __future__ import annotations

import base64
from typing import Any

import httpx

from .base import AudioInput, Transcript, TranscriptionError


class AliyunSpeechProvider:
    name = "aliyun"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "qwen3-asr-flash",
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Aliyun ASR API key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=120)
        self._owns_client = client is None

    async def transcribe(
        self,
        audio: AudioInput,
        *,
        language: str | None = None,
        vocabulary: list[str] | None = None,
    ) -> Transcript:
        del vocabulary
        data_uri = (
            f"data:{audio.content_type};base64,"
            f"{base64.b64encode(audio.content).decode('ascii')}"
        )
        asr_options: dict[str, Any] = {"enable_itn": True}
        if language:
            asr_options["language"] = language
        payload = {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"audio": data_uri}],
                    }
                ]
            },
            "parameters": {
                "result_format": "message",
                "asr_options": asr_options,
            },
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/services/aigc/multimodal-generation/generation",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            text = _extract_transcript_text(body)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise TranscriptionError("Aliyun speech transcription failed") from exc
        request_id = body.get("request_id")
        if not isinstance(request_id, str):
            request_id = response.headers.get("x-request-id")
        return Transcript(
            text=text,
            provider=self.name,
            model=self.model,
            language=language,
            provider_request_id=request_id,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


def _extract_transcript_text(body: dict[str, Any]) -> str:
    choices = body["output"]["choices"]
    content = choices[0]["message"]["content"]
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise ValueError("Aliyun response did not contain transcript text")
