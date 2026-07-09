# Dayboard API

FastAPI service for Dayboard.

## Local Commands

Start PostgreSQL and Redis from the repository root:

```bash
docker compose up -d postgres redis
```

Then run the API setup:

```bash
uv sync
uv run alembic upgrade head
uv run fastapi dev src/dayboard/main.py
```
