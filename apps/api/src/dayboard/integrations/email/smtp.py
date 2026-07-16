from __future__ import annotations

import asyncio
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl
from typing import Literal


class SmtpPasswordResetMailer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        security: Literal["starttls", "ssl", "plain"],
        from_address: str,
        from_name: str,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.security = security
        self.from_address = from_address
        self.from_name = from_name

    async def send_password_reset(
        self,
        *,
        recipient: str,
        reset_url: str,
        expires_minutes: int,
    ) -> None:
        message = self._build_message(
            recipient=recipient,
            reset_url=reset_url,
            expires_minutes=expires_minutes,
        )
        await asyncio.to_thread(self._send, message)

    def _build_message(
        self,
        *,
        recipient: str,
        reset_url: str,
        expires_minutes: int,
    ) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = "重置你的 Dayboard 密码"
        message["From"] = formataddr((self.from_name, self.from_address))
        message["To"] = recipient
        message.set_content(
            "你正在重置 Dayboard 密码。\n\n"
            f"请在 {expires_minutes} 分钟内打开以下链接：\n{reset_url}\n\n"
            "如果这不是你的操作，可以忽略这封邮件。"
        )
        return message

    def _send(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.security == "ssl":
            with smtplib.SMTP_SSL(
                self.host,
                self.port,
                timeout=15,
                context=context,
            ) as client:
                self._authenticate_and_send(client, message)
            return

        with smtplib.SMTP(self.host, self.port, timeout=15) as client:
            if self.security == "starttls":
                client.starttls(context=context)
            self._authenticate_and_send(client, message)

    def _authenticate_and_send(
        self,
        client: smtplib.SMTP,
        message: EmailMessage,
    ) -> None:
        if self.username:
            client.login(self.username, self.password or "")
        client.send_message(message)
