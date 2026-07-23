FROM python:3.11-slim AS build

ARG UV_VERSION=0.11.28

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/apps/api

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "uv==${UV_VERSION}"

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
COPY packages/agent-platform /workspace/packages/agent-platform
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

COPY apps/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.11-slim

ENV PATH=/app/.venv/bin:$PATH \
    HOME=/home/dayboard \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system dayboard \
    && useradd --system --create-home --home-dir /home/dayboard --gid dayboard --shell /usr/sbin/nologin dayboard

COPY --from=build --chown=dayboard:dayboard /workspace/apps/api/.venv ./.venv
COPY --chown=dayboard:dayboard apps/api/src ./src
COPY --chown=dayboard:dayboard apps/api/alembic.ini ./alembic.ini
COPY --chown=dayboard:dayboard apps/api/alembic ./alembic

USER dayboard

EXPOSE 8000

CMD ["fastapi", "run", "src/dayboard/main.py", "--host", "0.0.0.0", "--port", "8000"]
