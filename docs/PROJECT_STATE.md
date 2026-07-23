# Project State

This file is intentionally short. It is a release-facing summary, not an architecture document or
implementation chronology. Current facts live under [current](./current/README.md), decisions under
[adr](./adr/README.md), and expired plans under [archive](./archive/README.md).

## Current Version

- Development line: `0.3.x`; latest release tag: `v0.3.16`.
- Product: self-service Dayboard web application at `/dayboard/` with a same-site FastAPI API.
- Runtime: PostgreSQL, Redis, FastAPI, arq Worker, and Next.js managed by Docker Compose.
- Scheduling policy: any resolvable date or time creates a calendar entry; date-only entries use the
  native `anytime` shape; actions without a temporal anchor create tasks.
- Live execution: North `RunExecutor` publishes canonical chunks through Redis Streams; FastAPI
  exposes projected SSE events; PostgreSQL stores authoritative Run and conversation state.
- Frontend: Next.js, OpenAPI-generated `openapi-fetch`, TanStack Query, shadcn/ui primitives, and a
  validated discriminated Run-event reducer.

## Completed

- Added the authenticated reminder center with durable unread state, unread count, schedule-source
  navigation, failed-delivery retry, foreground browser Notifications, and tenant-isolated
  Reminder APIs.
- Added automatic FastAPI-to-Web OpenAPI drift enforcement, typed REST transport across Auth, Voice,
  Schedule, Reminder, Conversation, and Run recovery, TanStack Query pagination/invalidation, and a
  validated discriminated SSE event boundary.
- Added the critical Playwright browser gate, including deterministic SSE, active-Run recovery,
  clarification resume, optimistic edit/undo, and fixed-audio voice coverage.
- Expanded CI and release quality jobs to run the complete PostgreSQL API suite and browser E2E.
- Added a versioned 128-case Chinese scheduling Agent Eval with quantitative quality, safety,
  latency, and token metrics.
- Password registration/login, server sessions, password recovery, tenant/owner isolation, and
  endpoint-specific abuse limits.
- Natural-language create, search, reschedule, cancel, complete, multi-command execution, and
  structured clarification across calendar entries and tasks.
- Timed and `anytime` calendar entries, optimistic concurrency, idempotent Agent writes, conflict
  checks, reminder synchronization, and tenant-scoped schedule query APIs.
- Durable threads, bounded context, compaction summaries, queued Runs, cancellation, stale-Run
  recovery, provider usage settlement, and request/Run/tool correlation.
- Redis StreamBridge delivery with replay cursors, replay-gap recovery, safe tool-result projection,
  persisted conversation parts, and reconnectable browser SSE.
- Introduced the `agent_platform` package and moved trusted identity plus storage-independent
  Conversation/Run contracts and services out of the Dayboard product namespace.
- Added an explicit shared Unit of Work, atomic idempotent command submission, rollback-safe claim
  reuse, and concurrency-safe durable Run-event sequence allocation.
- Responsive conversation/day-view UI with direct mobile view dragging, streamed search-result rows,
  voice recording and ASR adapters, direct schedule editing, dark mode, settings drawer, generated
  API schema, and 600-line frontend source enforcement.
- Daily local PostgreSQL backups with checksums, retention, and a successful restore rehearsal.

## Next Milestone

Architecture hardening and public-release completion:

1. Add versioned artifact envelopes and atomically resolved Interaction contracts before extracting
   more product orchestration.
2. Design Service Worker/Web Push subscriptions and delivery for installed PWA.
3. Complete Chrome and Safari voice acceptance with non-sensitive Chinese schedule phrases.
4. Finish live Agent acceptance for relative dates, reminders, and change/cancel flows after the
   provider budget window allows it.
5. Measure Northgate prompt-cache effectiveness and move scoped provider-token policy to the
   gateway only after all production traffic uses it without direct-provider fallback.
6. Add encrypted off-host PostgreSQL backup replication and rehearse recovery from that copy.

Detailed active token and gateway work is tracked in [TODO.md](./TODO.md).

## Known Issues

- Installed-PWA background notifications are not implemented; browser Notifications currently
  require the authenticated Web app to be active.
- The last reference one-write Agent Run used 10,362 tokens over two model calls; cache-hit and
  per-round growth measurements are still incomplete.
- Dayboard still owns provider-token admission; Northgate does not yet enforce tenant/user/model
  scoped budgets for all traffic.
- Versioned presentation envelopes and atomically consumed Interaction state have not yet crossed
  the Platform package boundary.
- Scheduling defaults to trusted `Asia/Shanghai`; explicit foreign-timezone conversion is unsupported.
- Browser voice behavior has provider smoke coverage but not the full Chrome/Safari release matrix.
- Backups are host-local; encrypted off-host replication is pending.

## Release Check

Before tagging or deploying a release:

- [ ] Confirm `main` contains the intended migration and generated OpenAPI schema.
- [ ] Run `npm run api:types:check`, `npm run lint`, `npm run typecheck`, and `npm run build` in
  `apps/web`.
- [ ] Run Ruff and the complete PostgreSQL-backed API suite against a database ending in `_test`.
- [ ] Run the critical Playwright E2E suite without screenshots or real microphone access.
- [ ] Run Alembic upgrade against the test database and review generated SQL for new migrations.
- [ ] Run the targeted Agent acceptance program when the change affects prompt/tool behavior.
- [ ] Build replacement Docker images before recreating containers.
- [ ] Verify API, Worker, PostgreSQL, and Redis health plus the `/dayboard` HTTP response.
- [ ] Confirm backup freshness and do not use `docker compose down -v`.

Commands and rollback procedures live in [deploy.md](./deploy.md); test policy lives in
[engineering-guidelines.md](./engineering-guidelines.md).
