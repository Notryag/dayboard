FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system dayboard \
    && useradd --system --create-home --home-dir /home/dayboard --gid dayboard --shell /usr/sbin/nologin dayboard

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV HOME=/home/dayboard

USER dayboard

EXPOSE 8000

CMD ["/app/.venv/bin/fastapi", "run", "src/dayboard/main.py", "--host", "0.0.0.0", "--port", "8000"]
