# Agent Notes

These notes are for coding agents working on Dayboard.

## Documentation Routing

- Start implementation tasks at `docs/README.md` and follow its task-based reading list.
- Read `docs/engineering-guidelines.md` before adding code.
- Before changing the frontend, also read the frontend sections routed by `docs/README.md`, including `docs/ui-design.md`.
- Treat `docs/PROJECT_STATE.md` as a current-status summary, not the canonical source for engineering or UI rules.

## Production Checkout And Runtime

- The active production checkout is `/home/zx/dayboard`. Do not deploy from `/root/dayboard`; it is
  a legacy checkout from the previous systemd deployment.
- Docker Compose owns PostgreSQL, Redis, API, Worker, and Web in production. The old
  `dayboard-api.service`, `dayboard-worker.service`, and `dayboard-web.service` units are disabled
  and must not be re-enabled.
- Read `docs/deploy.md`, especially "Production Handoff", before changing deployment files or
  restarting services.
- Never run `docker compose down -v` in production. The named PostgreSQL and Redis volumes contain
  product data.
- Build replacement images before recreating application containers so a build failure does not
  cause avoidable downtime.

## Engineering Preferences

- Prefer stable, mature dependencies over hand-rolled lightweight code when the dependency improves reliability, operability, or maintainability.
- Do not avoid a good dependency just to keep the dependency count low.
- Keep Dayboard product concepts out of `north`; Dayboard depends on `north`, and `north` must not depend on Dayboard.
- Keep PostgreSQL as the source of truth. Do not replace it with SQLite, JSON files, or in-memory storage for product behavior.
- Use `/root/deer-flow` as the primary design reference when evolving `north`, especially its model provider factory, async middleware chain, run manager, stream bridge, and thread/run API semantics.
- Adapt DeerFlow patterns deliberately instead of copying its Gateway application wholesale. Reusable model/runtime contracts belong in `north`; Dayboard keeps FastAPI routes, tenant/auth policy, PostgreSQL product persistence, and scheduling concepts.
- Prefer DeerFlow's run resource lifecycle for future API work: create returns immediately, stream creates and follows a run, join follows an existing run, wait blocks for final state, and cancel is explicit.

## Test Execution

- Do not run tests after routine small changes. Use diff review and relevant static checks by default.
- Run the smallest affected tests only at key moments: shared runtime or database contract changes, concurrency/idempotency work, substantial feature completion, production incident fixes, and release/deployment batches.
- Reserve full regression and live-model tests for broad high-risk changes or release verification.
- Unit tests may use fakes for database sessions, model invokers, provider gateways, and run services when testing orchestration, logging, budgeting, or status mapping.
- Repository tests, API persistence tests, and scheduling tool tests must still run against PostgreSQL.
- Tests must use `TEST_DATABASE_URL` with a database name ending in `_test`. The test suite refuses to run against the product database because fixtures truncate tables.
- Docker Compose provides PostgreSQL and Redis from `docker-compose.yml`.
- In the Codex sandbox, normal commands may not reach Docker or `localhost:5432`. If PostgreSQL-backed tests hang or time out in the sandbox, rerun them with an execution context that can access Docker-exposed local ports.
- Use `docker compose ps` to confirm `dayboard-postgres-1` and `dayboard-redis-1` are healthy before treating database test failures as code failures.

Useful commands:

```bash
cd /home/zx/dayboard
docker compose ps
cd apps/api
uv run pytest -q tests/test_agent_runs.py tests/test_scheduling_tools.py tests/test_commands_api.py
```

## Secrets

- Real provider keys and gateway URLs belong in `.env` or deployment secret stores only.
- Do not commit real `OPENAI_API_KEY`, `OPENAI_BASE_URL`, or local Codex credentials.
