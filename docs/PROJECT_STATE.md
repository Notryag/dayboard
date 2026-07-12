# Project State

This document is a current-status and planning summary. Canonical implementation rules live in [engineering-guidelines.md](./engineering-guidelines.md), UI rules live in [ui-design.md](./ui-design.md), and task-specific reading starts at [README.md](./README.md). If this summary becomes stale or conflicts with those documents, follow the canonical guideline and update this file.

## Current Status

Dayboard has completed its natural-language scheduling foundation and is now becoming a publicly
releasable product. Self-service password registration and the Next.js web app are deployed on the
same HTTPS site; the in-app reminder foundation is implemented but not yet rendered in the web UI.

The active production repository is `/home/zx/dayboard`. `/root/dayboard` is a legacy checkout from
the previous systemd deployment and must not be used for production changes.

Production runs PostgreSQL, Redis, FastAPI, arq Worker, and Next.js through the root
`docker-compose.yml`. The old Dayboard systemd application units are disabled and inactive. Nginx
continues to proxy the loopback-only API and Web ports. See [deploy.md](./deploy.md), section
"Production Handoff", before operating the deployment.

The Git history is the source of truth for the latest committed baseline; do not copy a
commit hash into this document because it becomes stale on the next change.

The current direction is:

- product name: Dayboard
- frontend: Next.js, React, TypeScript; the primary server-hosted path is `/dayboard/`, while
  Vercel remains an optional preview deployment
- first UI surface: mobile-first chat-style command screen
- voice status: the microphone is currently a visual placeholder; the provider-neutral upload API and Alibaba Cloud ASR adapter are implemented, while browser recording and live credential verification remain pending
- first UI design approach: CSS variables/design tokens before detailed UI expansion
- backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- agent runtime: `north`
- model gateway config: OpenAI-compatible environment variables in `.env`
- database: PostgreSQL
- queue/cache/stream fanout: Redis or Valkey
- worker: `arq` with Redis
- production runtime: Docker Compose for PostgreSQL, Redis, API, Worker, and Web; application
  containers run as non-root users and API/Worker have container health checks
- object storage: S3-compatible storage for voice audio and future attachments

## Important Decisions

The bullets below summarize decisions that affect current work; they do not replace the canonical engineering and UI guidelines linked above.

- Dayboard depends on `north`; `north` must not depend on Dayboard.
- `north` owns runtime concepts such as `StreamEvent` and `RunEvent`.
- Dayboard owns product concepts such as `CalendarEntry` and `TaskItem`.
- Do not use plain `Event` for Dayboard calendar data.
- PostgreSQL is the product source of truth.
- Redis or Valkey is infrastructure, not a source of truth.
- All product boundaries carry `TenantContext`; full tenant administration and dedicated tenant
  databases remain deferred.
- Agent tools should be narrow and explicit, such as `create_calendar_entry` and `create_task_item`.
- Voice recognition is a Dayboard input-layer integration. It should produce transcript text that enters the normal command flow.
- Next.js is the first UI. React Native can be revisited later.
- Mature third-party libraries are allowed and encouraged when they reduce implementation risk.
- shadcn/ui is the preferred first UI component-system candidate; use its CLI when selected.
- TanStack Query is the preferred first candidate for server state once API calls become non-trivial.
- Zustand or Jotai are acceptable candidates for shared client state when plain React state is no longer enough.
- The first UI should focus on the conversation surface only: message history, text input, voice action, and send action.
- Visual choices should use CSS variables or shadcn theme tokens rather than hard-coded component colors.
- Real provider credentials must stay in `.env` or a secret store and must not be committed.
- Application rate limiting belongs at the FastAPI boundary first, with provider-level budgets added before real LLM calls.
- Public self-service registration is intentional. Protect it with dedicated rate limits, login
  abuse controls, provider budgets, tenant isolation, and observability rather than disabling it or
  requiring invitations by default.

## Next Milestone

Phase 1 has proved the natural-language scheduling loop. Continue public product readiness from
[phase-2-plan.md](./phase-2-plan.md). The coordinated account migration, same-site web/API
deployment, and production password-auth switch are complete. The minimal
today/tomorrow/open-task inspector is now connected to the structured query APIs. The
Run execution now reconnects after a page reload or a transient SSE disconnect. Stable API errors
remain the next reliability slice rather than reminder UI unless that priority changes.

## Implemented Capabilities

- Scheduling: natural-language create, search, reschedule, complete, and cancel for calendar entries
  and tasks, including multiple instructions per message and structured clarification; tenant-scoped
  calendar/task read APIs support time or status filters and keyset pagination for inspectable UI.
- Reliability: PostgreSQL source of truth, tenant scoping, optimistic concurrency, per-operation
  idempotency, queued arq execution, cancellation, stale-run recovery, reconnectable SSE execution,
  and health checks.
- Conversations: durable threads and messages, resumable clarification state, bounded context, and
  persisted compaction summaries.
- Agent runtime: North-backed execution, safe tool progress events, durable Run history, SSE,
  provider budgets, normalized token accounting, and exactly-once usage settlement.
- Identity: FastAPI password accounts, Argon2id credentials, server-side sessions, memberships,
  profiles, reusable web login state, and two-user HTTP/SSE ownership acceptance.
- Inspectable UI: a reusable schedule panel exposes today, tomorrow, and open tasks with account-
  timezone day boundaries, empty/error states, and cursor pagination.
- Observability: request IDs plus tenant, user, thread, Run, runtime/tool, and created-object
  correlation without logging credentials or full command text.
- Reminders: fixed-duration intent normalization, transactional PostgreSQL outbox synchronization,
  tenant-scoped status API, SKIP LOCKED worker claiming, and idempotent in-app delivery.
- Voice: provider-neutral transcription API and Alibaba Cloud ASR adapter; browser capture and live
  credential acceptance remain pending.

Git history is the detailed implementation chronology. ADRs record decisions that remain
architecturally significant.

Implementation notes:

- `CommandService` now calls `north.invoke_agent_once` directly; the old runtime placeholder path has been removed.
- Tests can still inject a fake service or fake invoker to avoid live model calls.
- Do not add natural-language interpretation outside the north-backed executor path.
- Provider budget admission reserves a cheap prompt-size estimate. The first immutable usage settlement charges any positive difference between actual and estimated tokens; lower provider-reported usage does not trigger an unsafe cross-window refund.
- A live `gpt-5.4-mini` smoke test has verified tool calling, clarification status mapping, and persisted provider usage through the configured OpenAI-compatible gateway.
- A live cross-process arq smoke test returned a queued run in about 35 ms and then emitted created, started, and clarification events over SSE.
- The current release defaults each entry's timezone to the trusted user timezone. Explicit natural-language event timezones such as "9 AM New York time" are not supported yet and must not be inferred as the user's default timezone.

Next implementation slice:

1. harden open registration, login, command, and voice endpoints for a public release
2. resume `calendar-changes` and `task-changes` acceptance after the provider budget window resets
3. add stable API errors; reminder UI and external notification providers remain explicitly deferred

Use scaffolding tools where available. Do not manually recreate boilerplate that a maintained CLI can generate.

## Verification

Reference verification commands are listed below. Follow the test policy in
[engineering-guidelines.md](./engineering-guidelines.md): use the smallest affected checks for a
normal slice and reserve full regression or live-model runs for release and high-risk changes.

```bash
cd apps/web && npm run lint
cd apps/web && npm run build
cd apps/api && uv sync
cd apps/api && uv run ruff check .
cd apps/api && uv run pytest -q tests/<affected_test_file>.py
cd apps/api && uv run python -c "from north import invoke_agent_once; print(invoke_agent_once)"
cd apps/api && uv run alembic upgrade head
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
  "database": "ok",
  "redis": "ok",
  "worker": "ok"
}
```

PostgreSQL, Redis, API, Worker, and Web are running through Docker Compose after verification. API,
Worker, PostgreSQL, and Redis report healthy; Web is verified through its `/dayboard` HTTP response.
The legacy Dayboard systemd application units remain disabled and inactive.

PostgreSQL-backed tests require access to the Docker-exposed PostgreSQL port. In Codex sandboxed command contexts, normal commands may not reach Docker or `localhost:5432`; if these tests hang or time out, rerun them from an execution context that can access Docker-exposed local ports after confirming `docker compose ps` reports healthy PostgreSQL and Redis containers.

Tests use `TEST_DATABASE_URL` and refuse database names that do not end in `_test`. Run Alembic migrations against the test database before the suite; test fixtures intentionally truncate test tables between cases.

## Testing Direction

Use slice-based testing:

```text
small implementation slice
  -> deterministic tests for domain, repository, or tool behavior
  -> API tests once endpoint exists
  -> limited agent-flow tests after tool behavior is stable
```

Add coverage in proportion to risk and do not make most tests depend on real LLM calls. Routine
small edits use diff review and static checks; database, shared runtime, authentication, release,
and production-incident changes use focused tests at the relevant key moment.

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

- worker deployment sizing and stale-running recovery policy
- exact first UI component install set: shadcn/ui components, icons, form tools, and state libraries
- final brand palette and detailed visual identity
- social login provider after the initial password-auth release (for example WeChat)
- first external notification provider after the in-app reminder surface
