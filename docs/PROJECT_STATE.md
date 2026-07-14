# Project State

This document is a current-status and planning summary. Canonical implementation rules live in [engineering-guidelines.md](./engineering-guidelines.md), UI rules live in [ui-design.md](./ui-design.md), and task-specific reading starts at [README.md](./README.md). If this summary becomes stale or conflicts with those documents, follow the canonical guideline and update this file.

## Current Status

Dayboard has completed its natural-language scheduling foundation and is now becoming a publicly
releasable product. Self-service password registration and the Next.js web app are deployed on the
same HTTPS site; the in-app reminder foundation is implemented but not yet rendered in the web UI.

The active production repository is `/home/zx/dayboard`. Other checkouts must not be used for
production changes.

Production runs PostgreSQL, Redis, FastAPI, arq Worker, and Next.js through the root
`docker-compose.yml`. Docker Compose is the only application process manager. Nginx proxies the
loopback-only API and Web ports. Read [deploy.md](./deploy.md) before operating the deployment.

The production host also runs the `dayboard-postgres-backup.timer` systemd timer. It creates daily
custom-format PostgreSQL dumps under `/var/backups/dayboard/postgres` with SHA-256 checksums and a
14-day retention period. A restore rehearsal into a temporary database has passed. These backups
are currently host-local; encrypted off-host replication remains pending.

The Git history is the source of truth for the latest committed baseline; do not copy a
commit hash into this document because it becomes stale on the next change.

The current direction is:

- product name: Dayboard
- frontend: Next.js, React, TypeScript; the server-hosted path is `/dayboard/`
- primary UI surfaces: a voice-first conversation home and a date-selectable day view; mobile uses a
  persistent bottom Conversation/Schedule tab bar and desktop keeps both visible in a two-pane
  workspace
- voice status: browser recording, upload limits, release-to-transcribe-and-submit interaction, the
  provider-neutral API, and Cloudflare Workers AI plus Alibaba Cloud adapters are implemented;
  production uses Cloudflare `whisper-large-v3-turbo`, while browser sample-audio acceptance remains
  part of release verification
- UI design approach: semantic CSS variables with a cool neutral canvas, teal brand/primary actions,
  fuchsia AI/voice activity, blue calendar state, amber task state, and mint completion state
- backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- agent runtime: `north`
- model gateway config: OpenAI-compatible environment variables in `.env`
- database: PostgreSQL
- queue/cache/stream fanout: Redis or Valkey
- worker: `arq` with Redis
- production runtime: Docker Compose for PostgreSQL, Redis, API, Worker, and Web; application
  containers run as non-root users and API/Worker have container health checks
- database recovery: daily host-level PostgreSQL dumps scheduled by systemd, checksum validation,
  restore-to-new-database safety, and a documented temporary-database rehearsal
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
- Scheduling currently uses server-configured Beijing time (`Asia/Shanghai`). Agent tools and
  per-command browser requests cannot supply timezone or numeric UTC offsets; `TenantContext.timezone`
  remains the future extension point for a trusted tenant setting.
- Agent tools should be narrow and explicit, such as `create_calendar_entry` and `create_task_item`.
- Voice recognition is a Dayboard input-layer integration. It should produce transcript text that enters the normal command flow.
- Next.js is the first UI. React Native can be revisited later.
- Mature third-party libraries are allowed and encouraged when they reduce implementation risk.
- shadcn/ui is the preferred first UI component-system candidate; use its CLI when selected.
- TanStack Query is the preferred first candidate for server state once API calls become non-trivial.
- Zustand or Jotai are acceptable candidates for shared client state when plain React state is no longer enough.
- Conversation and the day view are equal first-level product surfaces. Keep them separate on mobile
  and visible together on desktop; do not return the day view to a hidden header dialog.
- Visual choices should use CSS variables or shadcn theme tokens rather than hard-coded component colors.
- Real provider credentials must stay in `.env` or a secret store and must not be committed.
- Application rate limiting belongs at the FastAPI boundary first, with provider-level budgets added before real LLM calls.
- Public self-service registration is intentional. Protect it with dedicated rate limits, login
  abuse controls, provider budgets, tenant isolation, and observability rather than disabling it or
  requiring invitations by default.

## Next Milestone

Phase 1 has proved the natural-language scheduling loop. Continue public product readiness from
[phase-2-plan.md](./phase-2-plan.md). The coordinated account migration, same-site web/API
deployment, and production password-auth switch are complete. The application shell now uses a
conversation-first mobile home with a bottom Conversation/Schedule tab bar and a desktop
conversation/day-view workspace. The schedule panel has a
swipeable date rail, a chronological calendar/task agenda, and a separate undated-task area. Run
execution now reconnects after a page reload or a transient SSE
disconnect. API HTTP and validation errors now share a request-ID-bearing envelope, with stable
product codes for auth, thread, Run, command conflict, clarification conflict, and queue failure
paths.

## Implemented Capabilities

- Scheduling: natural-language create, search, reschedule, complete, and cancel for calendar entries
  and tasks, including multiple instructions per message and structured clarification; tenant-scoped
  calendar/task read APIs support product-local calendar dates, time/status/due-kind filters, and
  keyset pagination for inspectable UI. Calendar rescheduling can change date, start, and/or end
  time; omitted start/end semantics are deterministic and exact no-op updates are rejected.
- Reliability: PostgreSQL source of truth, tenant scoping, optimistic concurrency, per-operation
  idempotency, queued arq execution, cancellation, stale-run recovery, reconnectable SSE execution,
  stable API errors, health checks, daily database backups, and rehearsed restore tooling.
- Conversations: durable threads and messages, resumable clarification state, bounded context, and
  persisted compaction summaries.
- Agent runtime: North-backed execution, safe tool progress events, durable Run history, SSE,
  provider budgets, normalized token accounting, and exactly-once usage settlement.
- Identity: FastAPI password accounts, Argon2id credentials, server-side sessions, memberships,
  profiles, reusable web login state, production fail-closed configuration, endpoint-specific abuse
  limits, and tenant-plus-owner repository boundaries for conversations, Runs, schedules, tasks,
  transcripts, reminders, and provider usage.
- Inspectable UI: the responsive shell presents conversation and schedule as first-level views. A
  reusable day-view panel supports a native distant-date picker, a swipeable
  31-day rail, a chronological agenda merging calendar entries with dated tasks, and a separate
  undated/open-task list. The server owns trusted-timezone day boundaries; each source has
  independent loading, error, retry, stale-request cancellation, and cursor-pagination states.
- Calendar/task intent: the Agent treats concrete time blocks as calendar entries and
  completion-oriented actions as tasks. Vague timing such as "later" or "when free" remains an
  undated task, and independent actions in an unpunctuated voice transcript are split into tasks.
- Observability: request IDs plus tenant, user, thread, Run, runtime/tool, and created-object
  correlation without logging credentials or full command text.
- Reminders: fixed-duration intent normalization, transactional PostgreSQL outbox synchronization,
  tenant-scoped status API, SKIP LOCKED worker claiming, and idempotent in-app delivery.
- Voice: voice-first hold-to-talk composer with keyboard-mode fallback, slide-to-cancel, live
  level/timer, automatic duration stop, release-to-transcribe-and-submit commands, server-side
  format/size/duration validation, provider-neutral transcription API, and selectable Cloudflare
  Workers AI or Alibaba Cloud ASR adapters. Composer orchestration, voice gestures, text input, and
  MediaRecorder ownership have separate component/hook boundaries.

Git history is the detailed implementation chronology. ADRs record decisions that remain
architecturally significant.

Implementation notes:

- A live Cloudflare Workers AI smoke test verified the production credential, request correlation,
  Chinese transcription, and equivalent results for MP3, WebM/Opus, M4A/AAC, and OGG/Opus input.
  Server-side transcoding is therefore not required for the current browser recording formats.
- `CommandService` now calls `north.invoke_agent_once` directly; the old runtime placeholder path has been removed.
- Tests can still inject a fake service or fake invoker to avoid live model calls.
- Do not add natural-language interpretation outside the north-backed executor path.
- Provider budget admission reserves a cheap prompt-size estimate. The first immutable usage settlement charges any positive difference between actual and estimated tokens; lower provider-reported usage does not trigger an unsafe cross-window refund.
- A live `gpt-5.4-mini` smoke test has verified tool calling, clarification status mapping, and persisted provider usage through the configured OpenAI-compatible gateway.
- A live cross-process arq smoke test returned a queued run in about 35 ms and then emitted created, started, and clarification events over SSE.
- The current release resolves Agent-provided local calendar/task times with server-configured
  `Asia/Shanghai`. Agent schemas reject `Z` and numeric offsets, browser registration no longer
  supplies scheduling timezone, and stored objects retain aware timestamps plus the IANA name.
  Explicit natural-language timezones such as "9 AM New York time" are not supported.
- Relative date references are rendered as exact trusted-product-local dates in every agent system prompt.
  Agent-created calendar entries deterministically default to an at-start `PT0M` reminder; explicit
  advance offsets override it and an explicit no-reminder request can pass `null`. Final
  confirmations are instructed to use returned object values. Relative-date and confirmation model
  behavior still requires live acceptance; reminder defaults, end-time updates, and no-op rejection
  are server-enforced with focused coverage.
- When an assistant confirmation disagrees with stored scheduling data, correlate `agent_runs`,
  `agent_run_events`, and the calendar/task row. HTTP and worker logs intentionally omit command
  text; persisted `tool_call_started` events retain only allowlisted product inputs and are the
  authoritative diagnostic trace for model tool arguments.

Next implementation slice:

1. complete authenticated browser-to-transcript acceptance with non-sensitive Chinese recordings
   from Chrome and Safari, including date, time, and reminder phrases
2. add day-view item details and explicit actions, starting with event details and task completion;
   introduce narrow authenticated write APIs rather than routing deterministic UI actions through AI
3. after the provider budget window resets, run live acceptance for relative "tomorrow" dates,
   at-time reminders, end-time-only changes, then resume broader `calendar-changes` and
   `task-changes` acceptance
4. add encrypted off-host backup replication when storage credentials and retention requirements are
   available; keep circular visualization, reminder UI, and external notification providers deferred
   until priorities change

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
Application lifecycle is managed only through the root Docker Compose project.

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
