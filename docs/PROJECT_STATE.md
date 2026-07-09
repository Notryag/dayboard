# Project State

## Current Status

Dayboard has started implementation. M1 scaffolding is in place for the API, web app, local infrastructure, and initial database schema.

The current direction is:

- product name: Dayboard
- frontend: Next.js, React, TypeScript
- first UI surface: mobile-first chat-style command screen
- first UI design approach: CSS variables/design tokens before detailed UI expansion
- backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- agent runtime: `north`
- database: PostgreSQL
- queue/cache/stream fanout: Redis or Valkey
- worker candidate: `arq`
- object storage: S3-compatible storage for voice audio and future attachments

## Important Decisions

- Dayboard depends on `north`; `north` must not depend on Dayboard.
- `north` owns runtime concepts such as `StreamEvent` and `RunEvent`.
- Dayboard owns product concepts such as `CalendarEntry` and `TaskItem`.
- Do not use plain `Event` for Dayboard calendar data.
- PostgreSQL is the Phase 1 source of truth.
- Redis or Valkey is infrastructure, not a source of truth.
- Phase 1 should carry `TenantContext`, but not implement full tenant administration or dedicated tenant databases.
- Agent tools should be narrow and explicit, such as `create_calendar_entry` and `create_task_item`.
- Voice recognition is a Dayboard input-layer integration. It should produce transcript text that enters the normal command flow.
- Next.js is the first UI. React Native can be revisited later.
- Mature third-party libraries are allowed and encouraged when they reduce implementation risk.
- shadcn/ui is the preferred first UI component-system candidate; use its CLI when selected.
- TanStack Query is the preferred first candidate for server state once API calls become non-trivial.
- Zustand or Jotai are acceptable candidates for shared client state when plain React state is no longer enough.
- The first UI should focus on the conversation surface only: message history, text input, voice action, and send action.
- Visual choices should use CSS variables or shadcn theme tokens rather than hard-coded component colors.

## Next Milestone

Continue M1/M2 from [phase-1-plan.md](./phase-1-plan.md).

Completed M1 work:

- scaffolded `apps/api` with FastAPI, SQLAlchemy, Alembic, and local `north` dependency
- scaffolded `apps/web` with Next.js, React, TypeScript, and `lucide-react`
- added `TenantContext`
- added `CalendarEntry` and `TaskItem` domain schemas
- added PostgreSQL session wiring
- added repository foundations for calendar entries and task items
- added Alembic baseline migration
- added Docker Compose for PostgreSQL and Redis
- added the first mobile-first conversation UI

Next implementation slice:

1. add application services for calendar entries and task items
2. add deterministic `create_calendar_entry` and `create_task_item` tools
3. add repository tests against PostgreSQL
4. add the first `POST /api/commands` placeholder flow without LLM calls

Use scaffolding tools where available. Do not manually recreate boilerplate that a maintained CLI can generate.

## Verification

Latest verified commands:

```bash
cd apps/web && npm run lint
cd apps/web && npm run build
cd apps/api && uv sync
cd apps/api && uv run ruff check .
cd apps/api && uv run python -c "from dayboard.main import app; from dayboard.context import get_dev_tenant_context; print(app.title, get_dev_tenant_context().timezone)"
cd apps/api && uv run alembic upgrade head --sql
docker compose up -d postgres redis
cd apps/api && uv run alembic upgrade head
cd apps/api && uv run fastapi dev src/dayboard/main.py --host 127.0.0.1 --port 8000
curl -sS http://127.0.0.1:8000/health
```

The `/health` response was:

```json
{
  "status": "ok",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "user_id": "00000000-0000-0000-0000-000000000002"
}
```

PostgreSQL and Redis are running through Docker Compose after verification.

## Testing Direction

Use slice-based testing:

```text
small implementation slice
  -> deterministic tests for domain, repository, or tool behavior
  -> API tests once endpoint exists
  -> limited agent-flow tests after tool behavior is stable
```

Do not wait until the end to add tests. Do not make most tests depend on real LLM calls.

## Do Not Change Without Discussion

- moving Dayboard business concepts into `north`
- renaming `CalendarEntry` back to `Event`
- replacing PostgreSQL with SQLite or JSON storage
- skipping tenant context in service and tool boundaries
- making Redis or Valkey the source of truth
- binding ASR directly into `north`
- starting with React Native instead of Next.js
- creating large boilerplate manually when a reliable scaffold exists

## Open Questions

- first worker implementation: `arq` or another queue
- exact first UI component install set: shadcn/ui components, icons, form tools, and state libraries
- final brand palette and detailed visual identity
- first ASR provider
- auth provider and login flow
- local development database setup
