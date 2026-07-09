from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dayboard.api.rate_limit import configure_rate_limiting
from dayboard.api.routes import router
from dayboard.config import get_settings
from dayboard.observability.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Dayboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    configure_rate_limiting(app, settings)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("dayboard.main:app", host="0.0.0.0", port=8000, reload=True)
