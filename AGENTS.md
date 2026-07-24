# Agent Notes

These notes are for coding agents working on Dayboard.

## Documentation Routing

- Start implementation tasks at `docs/README.md` and follow its task-based reading list.
- Treat `docs/current/` as the only canonical whole-system description. ADRs explain decisions;
  `docs/archive/` is historical and must not guide implementation.
- Read `docs/engineering-guidelines.md` before adding code.
- Before changing the frontend, also read the frontend sections routed by `docs/README.md`, including `docs/ui-design.md`.
- Keep `docs/PROJECT_STATE.md` limited to version, completed work, next milestone, known issues, and
  release checks.

## Production Checkout And Runtime

- The active production checkout is `/home/zx/dayboard`. Do not deploy from another checkout.
- Docker Compose owns PostgreSQL, Redis, API, Worker, and Web in production. Do not add another
  process manager for these application services.
- Read `docs/deploy.md` before changing deployment files or restarting services.
- Never run `docker compose down -v` in production. The named PostgreSQL and Redis volumes contain
  product data.
- Build replacement images before recreating application containers so a build failure does not
  cause avoidable downtime.

## Engineering Preferences

- Prefer stable, mature dependencies over hand-rolled lightweight code when the dependency improves reliability, operability, or maintainability.
- Do not avoid a good dependency just to keep the dependency count low.
- Follow [ADR-009](docs/adr/009-keep-platform-and-north-independent.md): Dayboard may import both
  `north` and `agent_platform`; the two lower-level packages do not import each other or Dayboard.
- Keep Dayboard product concepts out of both `north` and `agent_platform`. North owns runtime
  primitives, while `agent_platform` owns reusable application capabilities defined by ADR-008.
- Keep PostgreSQL as the source of truth. Do not replace it with SQLite, JSON files, or in-memory storage for product behavior.
- Use `/root/deer-flow` as the primary design reference when evolving `north`, especially its model provider factory, async middleware chain, run manager, stream bridge, and thread/run API semantics.
- Adapt DeerFlow patterns deliberately instead of copying its Gateway application wholesale.
  Reusable model/runtime contracts belong in `north`; reusable application contracts belong in
  `agent_platform`; Dayboard keeps scheduling policy, product persistence, prompts, tools, and UI.
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
