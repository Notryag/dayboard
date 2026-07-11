from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        candidate = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = candidate if _REQUEST_ID_PATTERN.fullmatch(candidate) else f"req_{uuid4().hex}"
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id.encode("ascii"))
                )
            await send(message)

        logger = structlog.get_logger("dayboard.request")
        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "dayboard.http.request_failed",
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        else:
            logger.info(
                "dayboard.http.request_completed",
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        finally:
            structlog.contextvars.clear_contextvars()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=_coerce_log_level(level),
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _coerce_log_level(level: str) -> int:
    resolved = getattr(logging, level.upper(), None)
    return resolved if isinstance(resolved, int) else logging.INFO
