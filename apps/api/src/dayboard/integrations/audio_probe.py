from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Protocol


class InvalidAudioError(ValueError):
    """The uploaded bytes do not contain readable audio metadata."""


class AudioProbeUnavailableError(RuntimeError):
    """The server cannot currently inspect uploaded audio."""


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    duration_ms: int


class AudioMetadataProbe(Protocol):
    async def inspect(self, content: bytes, *, content_type: str) -> AudioMetadata: ...


class PyavAudioMetadataProbe:
    _suffixes = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
    }

    def __init__(self, timeout_seconds: float = 10) -> None:
        self.timeout_seconds = timeout_seconds

    async def inspect(self, content: bytes, *, content_type: str) -> AudioMetadata:
        return await asyncio.to_thread(self._inspect_sync, content, content_type)

    def _inspect_sync(self, content: bytes, content_type: str) -> AudioMetadata:
        suffix = self._suffixes.get(content_type, ".audio")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "dayboard.integrations.audio_probe",
                    str(temporary_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioProbeUnavailableError("Audio metadata probe timed out") from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        if result.returncode == 2 or result.returncode < 0:
            raise AudioProbeUnavailableError("Audio metadata probe is not installed")
        if result.returncode != 0:
            raise InvalidAudioError("Audio metadata could not be read")
        try:
            duration_ms = int(result.stdout.strip())
        except ValueError as exc:
            raise InvalidAudioError("Audio duration is invalid") from exc
        if duration_ms <= 0:
            raise InvalidAudioError("Audio duration is invalid")
        return AudioMetadata(duration_ms=duration_ms)


def _duration_seconds(path: Path) -> float:
    import av

    with av.open(str(path), mode="r") as container:
        audio_stream = next((stream for stream in container.streams if stream.type == "audio"), None)
        if audio_stream is None:
            raise InvalidAudioError("Audio stream is missing")

        candidates: list[float] = []
        if container.duration is not None:
            candidates.append(float(container.duration / av.time_base))
        if audio_stream.duration is not None and audio_stream.time_base is not None:
            candidates.append(float(audio_stream.duration * audio_stream.time_base))

        packet_starts: list[float] = []
        packet_ends: list[float] = []
        for packet in container.demux(audio_stream):
            if packet.pts is None or packet.time_base is None:
                continue
            start = float(packet.pts * packet.time_base)
            duration = (
                float(packet.duration * packet.time_base)
                if packet.duration is not None
                else 0
            )
            packet_starts.append(start)
            packet_ends.append(start + duration)
        if packet_starts and packet_ends:
            candidates.append(max(packet_ends) - min(packet_starts))

    valid = [value for value in candidates if math.isfinite(value) and value > 0]
    if not valid:
        raise InvalidAudioError("Audio duration is invalid")
    return max(valid)


def _main() -> int:
    if len(sys.argv) != 2:
        return 1
    try:
        duration_ms = round(_duration_seconds(Path(sys.argv[1])) * 1000)
    except ImportError:
        return 2
    except Exception:
        return 1
    if duration_ms <= 0:
        return 1
    print(duration_ms)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
