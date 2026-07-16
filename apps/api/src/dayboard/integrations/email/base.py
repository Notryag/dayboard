from __future__ import annotations

from typing import Protocol


class PasswordResetMailer(Protocol):
    async def send_password_reset(
        self,
        *,
        recipient: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None: ...
