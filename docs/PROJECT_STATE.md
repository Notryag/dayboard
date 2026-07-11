# Project State

This document is a current-status and planning summary. Canonical implementation rules live in [engineering-guidelines.md](./engineering-guidelines.md), UI rules live in [ui-design.md](./ui-design.md), and task-specific reading starts at [README.md](./README.md). If this summary becomes stale or conflicts with those documents, follow the canonical guideline and update this file.

## Current Status

Dayboard has started implementation. M1 scaffolding is in place for the API, web app, local infrastructure, and initial database schema.

The repository is initialized at `/root/dayboard`.

The Git history is the source of truth for the latest committed baseline; do not copy a
commit hash into this document because it becomes stale on the next change.

The current direction is:

- product name: Dayboard
- frontend: Next.js, React, TypeScript
- first UI surface: mobile-first chat-style command screen
- voice status: the microphone is currently a visual placeholder; the provider-neutral upload API and Alibaba Cloud ASR adapter are implemented, while browser recording and live credential verification remain pending
- first UI design approach: CSS variables/design tokens before detailed UI expansion
- backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- agent runtime: `north`
- model gateway config: OpenAI-compatible environment variables in `.env`
- database: PostgreSQL
- queue/cache/stream fanout: Redis or Valkey
- worker: `arq` with Redis
- object storage: S3-compatible storage for voice audio and future attachments

## Important Decisions

The bullets below summarize decisions that affect current work; they do not replace the canonical engineering and UI guidelines linked above.

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
- Real provider credentials must stay in `.env` or a secret store and must not be committed.
- Application rate limiting belongs at the FastAPI boundary first, with provider-level budgets added before real LLM calls.

## Next Milestone

Phase 1 has proved the natural-language scheduling loop. Continue the usable account beta from
[phase-2-plan.md](./phase-2-plan.md), starting with authenticated identity and ownership.

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

Completed M2 work:

- added `SchedulingService` for calendar entries and task items
- added deterministic scheduling tool adapters:
  - `create_calendar_entry`
  - `list_calendar_entries`
  - `create_task_item`
  - `list_task_items`
- added PostgreSQL-backed tests for the create/list tool paths
- added and later removed the temporary synchronous command placeholder
- reduced command input to natural-language text interpreted only by north
- added OpenAI-compatible model gateway configuration placeholders
- added Redis-backed FastAPI rate limiting configuration
- connected the Next.js composer to queued command creation and SSE terminal events
- added local CORS configuration for Next.js dev origins
- added `agent_runs` and `agent_run_events` persistence
- added `AgentRunService` and run event repositories
- added `GET /api/runs/{run_id}` and `GET /api/runs/{run_id}/events`
- changed the temporary command path to create real run records and lifecycle events
- added Dayboard agent assembly boundary around `north.build_agent`
- added replaceable command executor boundary so the placeholder can be swapped for a north-backed executor
- added LangChain/north-compatible scheduling tool wrappers with server-injected session, tenant context, and run id
- removed `created_by_run_id` from model-visible scheduling tool input
- added provider-level request and estimated token budget guard before real model calls
- added a provider-neutral speech-to-text boundary, persisted voice transcription API, and Alibaba Cloud `qwen3-asr-flash` adapter; real transcription requires a China-region Model Studio API key
- added generic `north.invoke_agent_once` helper in the reusable `north` package
- implemented `CommandService` to create Dayboard runs, check provider budgets, build Dayboard scheduling tools, invoke `north`, and map completion or clarification results back to run events
- added a PostgreSQL provider usage ledger that records actual input, output, and total tokens reported by LangChain model messages
- added an SSE run-event endpoint with incremental replay, keep-alives, and terminal-event closure
- verified `gpt-5.4-mini` live tool selection for calendar creation and clarification through the configured gateway
- added `POST /api/command-runs`, which commits a queued run and returns 202 before execution
- added an arq command dispatcher and independent Redis-backed worker sessions
- removed the old synchronous `/api/commands` path and temporary structured intent input
- added a one-hour default duration for calendar entries without an explicit end time
- added deterministic, tenant-scoped calendar overlap checks before creation
- added non-blocking conflict warnings while preserving default calendar creation
- added persisted tool progress events and rendered their SSE-driven execution trace in the web UI
- required timezone-aware datetimes at domain and agent-tool boundaries; PostgreSQL stores canonical instants while each calendar entry retains its intended IANA timezone
- added database-enforced scheduling write idempotency keyed by tenant and creating run
- added `Idempotency-Key` support for command creation so retried requests return the original run without duplicate queue delivery
- added explicit Run cancellation with durable lifecycle events, best-effort arq job abortion, worker-side cancellation checks, and a web stop control
- added periodic stale-running recovery that closes timed-out runs as failed with a durable recovery event
- expanded `/health` to verify PostgreSQL, Redis, and the arq worker heartbeat
- added seven-day idempotency-key retention with a scheduled cleanup job and structured operational logs
- added a DeerFlow-inspired `north.RuntimeJournal` integration that captures model/tool callbacks and projects allowlisted, user-safe execution events into Dayboard Run history
- added tenant-scoped calendar search and safe rescheduling that preserves duration, event timezone, participants, and reminders, with optimistic concurrency, Run idempotency, and update audit attribution
- added reliable calendar cancellation with search-first targeting, optimistic concurrency, Run idempotency, and audit attribution
- added PostgreSQL-backed conversation history, resumable structured clarification, bounded agent context, and persisted compaction summaries
- added task search and natural-language task updates for title, due time, completion, and cancellation, with optimistic concurrency, per-operation Run idempotency, and update audit attribution
- extended calendar rescheduling and cancellation to per-operation Run idempotency so one command can safely modify multiple entries
- moved provider token normalization and per-call aggregation into north runtime events; Dayboard persists the normalized totals with tenant, user, model, and Run attribution
- added independent finalization-time provider usage settlement for successful, clarification, failed, interrupted, and cancelled Runs, with one immutable tenant/Run record
- reconciled the pre-call token reservation with first-settled actual usage by charging any positive difference exactly once
- added an explicit live Agent acceptance runner for multi-create, calendar/task changes, missing targets, durable tool events, status, and latency
- isolated runtime callback event persistence from the Agent tool transaction and serialized per-Run event writes, preventing concurrent AsyncSession use during parallel tool calls
- production acceptance passed mixed multi-create after the 202607110005 deployment; calendar change acceptance was blocked before tool execution by repeated upstream model-gateway 503 responses, with no recurrence of the AsyncSession callback concurrency error
- serialized Dayboard scheduling tool execution within each Run after production task acceptance exposed LangGraph parallel tool calls sharing one business AsyncSession
- production re-verification confirmed two parallel task creates succeed after tool serialization; remaining calendar/task change acceptance stopped at the configured 60000/day provider token budget without calling the model, and must resume after the budget window resets or with a separately budgeted acceptance tenant
- selected FastAPI-native username/password authentication for the first beta, using Argon2id password hashes, revocable server-side sessions, Dayboard-owned tenants and memberships, and a provider-neutral external identity extension point
- added validated request IDs, structured request completion/failure logs, authenticated user/tenant log context, and request-to-thread-to-Run correlation without logging command text or authentication secrets
- removed caller-supplied tenant headers from the API rate-limit identity boundary
- added a reusable web authentication provider and credentialed API client, with register, login,
  logout, session recovery, request-reference errors, and credentialed SSE support; production
  release remains blocked on a same-site web/API domain and coordinated auth-mode switch

Implementation notes:

- `CommandService` now calls `north.invoke_agent_once` directly; the old runtime placeholder path has been removed.
- Tests can still inject a fake service or fake invoker to avoid live model calls.
- Do not add natural-language interpretation outside the north-backed executor path.
- Provider budget admission reserves a cheap prompt-size estimate. The first immutable usage settlement charges any positive difference between actual and estimated tokens; lower provider-reported usage does not trigger an unsafe cross-window refund.
- A live `gpt-5.4-mini` smoke test has verified tool calling, clarification status mapping, and persisted provider usage through the configured OpenAI-compatible gateway.
- A live cross-process arq smoke test returned a queued run in about 35 ms and then emitted created, started, and clarification events over SSE.
- The current release defaults each entry's timezone to the trusted user timezone. Explicit natural-language event timezones such as "9 AM New York time" are not supported yet and must not be inferred as the user's default timezone.

Next implementation slice:

1. configure a same-site production web/API domain, then run two-user HTTP and SSE isolation acceptance before switching production from `development` to `password` auth mode
2. resume `calendar-changes` and `task-changes` acceptance after the provider budget window resets
3. implement one reliable reminder delivery channel now that authenticated user profiles exist

Use scaffolding tools where available. Do not manually recreate boilerplate that a maintained CLI can generate.

## Verification

Latest verified commands:

```bash
cd apps/web && npm run lint
cd apps/web && npm run build
cd apps/api && uv sync
cd apps/api && uv run ruff check .
cd apps/api && uv run pytest
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

PostgreSQL and Redis are running through Docker Compose after verification.

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

- worker deployment sizing and stale-running recovery policy
- exact first UI component install set: shadcn/ui components, icons, form tools, and state libraries
- final brand palette and detailed visual identity
- first ASR provider
- social login provider after password-auth beta (for example WeChat)
- local development database setup
