from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from dayboard.api.rate_limit import configure_rate_limiting
from dayboard.api.routes import router
from dayboard.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Dayboard API", version="0.1.0")
    configure_rate_limiting(app, get_settings())
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("dayboard.main:app", host="0.0.0.0", port=8000, reload=True)
