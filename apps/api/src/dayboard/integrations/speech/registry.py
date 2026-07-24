from __future__ import annotations

from collections.abc import Callable

from dayboard.app.voice_ports import SpeechToTextProvider

ProviderFactory = Callable[[], SpeechToTextProvider]


class SpeechProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Speech provider name must not be empty")
        if normalized in self._factories:
            raise ValueError(f"Speech provider {normalized!r} is already registered")
        self._factories[normalized] = factory

    def create(self, name: str) -> SpeechToTextProvider:
        normalized = name.strip().lower()
        factory = self._factories.get(normalized)
        if factory is None:
            available = ", ".join(sorted(self._factories)) or "none"
            raise LookupError(
                f"Speech provider {normalized!r} is not registered; available: {available}"
            )
        return factory()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
