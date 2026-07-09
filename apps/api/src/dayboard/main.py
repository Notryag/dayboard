from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from dayboard.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Dayboard API", version="0.1.0")
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run("dayboard.main:app", host="0.0.0.0", port=8000, reload=True)
