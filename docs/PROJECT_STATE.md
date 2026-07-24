# Project State

This file is intentionally short. It is a release-facing summary, not an architecture document or
implementation chronology. Current facts live under [current](./current/README.md), decisions under
[adr](./adr/README.md), and expired plans under [archive](./archive/README.md).

## Current Version

- Development line: `0.3.x`; latest deployed release tag: `v0.3.19`.
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
- Added versioned resumable Interactions, Dayboard-owned typed clarification payloads, safe generated
  Web state contracts, and atomic compare-and-consume continuation submission with retry recovery.
- Replaced unversioned assistant message metadata with Platform-owned versioned Presentation
  envelopes, Dayboard-owned validated schedule payloads, generated Web history types, and identical
  live-versus-refresh schedule-card recovery.
- Separated Conversation Thread lifecycle from primary identity with a constrained
  `active | archived` status, explicit `is_primary`, one-time data migration, and active-only command
  submission while preserving archived history reads and idempotent retries.
- Reconciled legacy JSON storage with the ORM's JSONB contract, declared North checkpoint tables as
  externally owned, and made `alembic check` a CI schema-drift gate.
- Replaced unversioned durable Run-event metadata with Platform-owned Event Extension envelopes and
  typed North model/tool plus Platform failure/interaction-state payloads.
- Added a product-neutral Platform Run execution coordinator with atomic terminal persistence,
  a Dayboard-owned North driver and result projector, database-authoritative `run_id`-only jobs, and
  no superseded execution compatibility path.
- Added a product-owned Scheduling Unit of Work: application services now consume domain store
  ports, SQLAlchemy repositories return domain objects, and calendar/task changes commit atomically
  with Reminder Outbox replacement at the API or Agent boundary.
- Added a separate product-owned Reminder Unit of Work: inbox and Worker services consume delivery
  and source-projection ports, queue state remains private, expired calendar notifications are
  distinct from cancelled sources, and inbox items use the current authoritative source snapshot.
- Added a product-owned Voice Unit of Work and provider port: application code receives domain
  transcripts, tenant-scoped repositories own ORM mapping, and no database transaction remains open
  while the external ASR provider runs.
- Added a Dayboard-owned Account Recovery Unit of Work: reset issue/consumption return storage-free
  records, API boundaries own commit/rollback, and User-row locking serializes token replacement,
  password reset, and session revocation. Login verifies an unlocked credential snapshot outside
  the database transaction, then briefly locks and revalidates it before creating a Session.
- Provider Usage crosses a narrow settlement port. Its SQLAlchemy adapter owns one independent
  short transaction, owner-scoped insertion is concurrent and idempotent, ORM rows stay in the
  repository, and accounting failures cannot replace an authoritative terminal Run outcome.
- Moved Platform and Run construction to explicit composition roots: FastAPI dependencies build the
  storage-free command service, Workers build one North driver per Run, and runtime journal events
  use fresh Platform Unit-of-Work sessions rather than sharing the execution session.
- Responsive conversation/day-view UI with direct mobile view dragging, streamed search-result rows,
  voice recording and ASR adapters, direct schedule editing, dark mode, settings drawer, generated
  API schema, and 600-line frontend source enforcement.
- Daily local PostgreSQL backups with checksums, retention, and a successful restore rehearsal.

## Next Milestone

Architecture hardening and public-release completion:

1. Complete Chrome and Safari voice acceptance with non-sensitive Chinese schedule phrases.
2. Finish live Agent acceptance for relative dates, reminders, and change/cancel flows after the
   provider budget window allows it.
3. Measure Northgate prompt-cache effectiveness and move scoped provider-token policy to the
   gateway only after all production traffic uses it without direct-provider fallback.
4. Add encrypted off-host PostgreSQL backup replication and rehearse recovery from that copy.

Detailed active token and gateway work is tracked in [TODO.md](./TODO.md).

## Known Issues

- Installed-PWA background notifications are intentionally deferred; browser Notifications require
  the authenticated Web app to be active.
- The last reference one-write Agent Run used 10,362 tokens over two model calls; cache-hit and
  per-round growth measurements are still incomplete.
- Dayboard still owns provider-token admission; Northgate does not yet enforce tenant/user/model
  scoped budgets for all traffic.
- Scheduling defaults to trusted `Asia/Shanghai`; explicit foreign-timezone conversion is unsupported.
- Browser voice behavior has provider smoke coverage but not the full Chrome/Safari release matrix.
- An abrupt API process termination during an in-flight ASR request can leave its audit transcript
  in `processing`; ordinary request cancellation is finalized as `failed`, but stale-process
  recovery is deferred until Voice execution moves to a durable asynchronous lifecycle.
- Password-reset mail delivery is best effort after the token transaction commits. Concurrent reset
  requests can deliver messages out of order; only the newest token remains valid until a durable
  mail Outbox is introduced.
- A hard Worker exit before Provider Usage settlement can omit the aggregate. A crash after its
  PostgreSQL commit but before Redis budget reconciliation can leave the reservation inaccurate;
  durable usage recovery remains pending.
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
