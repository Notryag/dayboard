from __future__ import annotations

from fastapi import FastAPI, Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from dayboard.config import Settings


def rate_limit_key(request: Request) -> str:
    # Authentication runs inside endpoint dependencies, after this middleware.
    # Never trust a caller-supplied tenant header for abuse controls.
    return get_remote_address(request)


def configure_rate_limiting(app: FastAPI, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return

    limiter = Limiter(
        key_func=rate_limit_key,
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.effective_rate_limit_storage_url,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    del request
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    return Response(
        content='{"error":{"code":"rate_limit_exceeded","message":"Too many requests."}}',
        status_code=429,
        media_type="application/json",
    )
