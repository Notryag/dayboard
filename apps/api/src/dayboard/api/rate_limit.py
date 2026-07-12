from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from dayboard.config import Settings, get_settings
from dayboard.api.errors import ApiErrorBody, ApiErrorResponse


def rate_limit_key(request: Request) -> str:
    # Authentication runs inside endpoint dependencies, after this middleware.
    # Never trust a caller-supplied tenant header for abuse controls.
    return get_remote_address(request)


_settings = get_settings()
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[_settings.rate_limit_default],
    storage_uri=_settings.effective_rate_limit_storage_url,
    enabled=_settings.rate_limit_enabled,
)


def configure_rate_limiting(app: FastAPI, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    if not isinstance(exc, RateLimitExceeded):
        raise exc
    body = ApiErrorResponse(
        error=ApiErrorBody(
            code="RATE_LIMIT_EXCEEDED",
            message="Too many requests",
            request_id=getattr(request.state, "request_id", "unavailable"),
        )
    )
    return JSONResponse(
        content=body.model_dump(mode="json"),
        status_code=429,
    )
