from __future__ import annotations

from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dayboard.api.rate_limit import configure_rate_limiting
from dayboard.api.errors import configure_error_handling
from dayboard.api.auth import router as auth_router
from dayboard.api.routes import router
from dayboard.app.command_dispatcher import RedisCommandDispatcher
from dayboard.config import get_settings
from dayboard.integrations.speech import AliyunSpeechProvider, SpeechProviderRegistry
from dayboard.observability.logging import RequestContextMiddleware, configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.effective_command_queue_url))
    app.state.command_dispatcher = RedisCommandDispatcher(
        redis,
        queue_name=settings.command_queue_name,
    )
    speech_registry = SpeechProviderRegistry()
    if settings.aliyun_asr_api_key is not None:
        speech_registry.register(
            "aliyun",
            lambda: AliyunSpeechProvider(
                api_key=settings.aliyun_asr_api_key.get_secret_value(),
                model=settings.aliyun_asr_model,
                base_url=settings.aliyun_asr_base_url,
            ),
        )
    speech_provider = None
    if settings.asr_provider in speech_registry.names:
        speech_provider = speech_registry.create(settings.asr_provider)
        app.state.speech_provider = speech_provider
    try:
        yield
    finally:
        if speech_provider is not None:
            await speech_provider.aclose()
        await redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Dayboard API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    configure_error_handling(app)
    configure_rate_limiting(app, settings)
    app.include_router(auth_router)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("dayboard.main:app", host="0.0.0.0", port=8000, reload=True)
