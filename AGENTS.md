# Agent Notes

These notes are for coding agents working on Dayboard.

## Engineering Preferences

- Prefer stable, mature dependencies over hand-rolled lightweight code when the dependency improves reliability, operability, or maintainability.
- Do not avoid a good dependency just to keep the dependency count low.
- Keep Dayboard product concepts out of `north`; Dayboard depends on `north`, and `north` must not depend on Dayboard.
- Keep PostgreSQL as the source of truth. Do not replace it with SQLite, JSON files, or in-memory storage for product behavior.

## Test Execution

- Unit tests may use fakes for database sessions, model invokers, provider gateways, and run services when testing orchestration, logging, budgeting, or status mapping.
- Repository tests, API persistence tests, and scheduling tool tests must still run against PostgreSQL.
- Docker Compose provides PostgreSQL and Redis from `docker-compose.yml`.
- In the Codex sandbox, normal commands may not reach Docker or `localhost:5432`. If PostgreSQL-backed tests hang or time out in the sandbox, rerun them with an execution context that can access Docker-exposed local ports.
- Use `docker compose ps` to confirm `dayboard-postgres-1` and `dayboard-redis-1` are healthy before treating database test failures as code failures.

Useful commands:

```bash
cd /root/dayboard
docker compose ps
cd apps/api
uv run pytest -q tests/test_agent_runs.py tests/test_scheduling_tools.py tests/test_commands_api.py
```

## Secrets

- Real provider keys and gateway URLs belong in `.env` or deployment secret stores only.
- Do not commit real `OPENAI_API_KEY`, `OPENAI_BASE_URL`, or local Codex credentials.
