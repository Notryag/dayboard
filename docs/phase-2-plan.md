# Phase 2 Plan: Public Product Readiness

## Product Goal

Move Dayboard from a shared-user technical MVP to a releasable product where anyone can create an
account and safely manage their own schedules and reminders.

Phase 1 proved the Agent loop. Phase 2 is not primarily an Agent-capability phase. It closes
the product boundaries required for real use: identity, ownership, personal settings, reminder
delivery, abuse protection, and a minimal inspectable experience.

Public self-service registration is an intentional product capability. It must remain available in
production. Release protection should come from identity isolation, endpoint-specific rate limits,
login abuse protection, provider budgets, and operational visibility rather than an invitation gate.

## Current Product Assessment

The natural-language scheduling backend is an MVP-quality closed loop:

- create, find, change, complete, and cancel calendar entries and tasks;
- execute multiple instructions from one message;
- clarify ambiguous targets with structured choices;
- persist conversations and bounded Agent context;
- expose durable Run progress and safe tool observability;
- protect writes with tenant scoping, idempotency, optimistic concurrency, and audit fields;
- run API, worker, PostgreSQL, Redis, migrations, usage accounting, and budgets in production.

Password authentication, self-service registration, tenant ownership, and the same-site web/API
deployment are running in production. The scheduling backend is ahead of the product surface: users
still need an inspectable calendar/task view, reconnectable Run execution, stable error handling,
and release-grade abuse controls. The reminder inbox is not rendered, and browser voice capture is
not connected.

## Milestone Order

### P2.1 Real Identity And Ownership

Status: backend, web session flow, isolation acceptance, and production enablement complete.

Completed:

- username/password registration and login in FastAPI;
- Argon2id password hashes and revocable server-side sessions in `HttpOnly` cookies;
- Dayboard users, memberships, timezone/locale profiles, and an external-identity extension point;
- trusted `TenantContext` resolution from sessions and memberships;
- minimal web registration, login, logout, session recovery, and credentialed SSE;
- two-user ownership acceptance for threads and Run status, events, streaming, and cancellation.

Remaining:

- run the expanded same-tenant/different-owner acceptance set at the next release gate;

Production startup rejects development auth or insecure cookies. Registration, login, command, and
voice endpoints have separate Redis-backed abuse limits without disabling public registration.
Repository access for conversations, Runs, calendar entries, tasks, transcripts, reminders, and
provider usage is constrained by both tenant and owner. The Run and provider-usage boundaries were
tightened after a repository audit.

Completion means two users cannot read, mutate, stream, or infer each other's data, and a
production deployment cannot start in development-auth mode by accident.

Backend acceptance now covers password-session isolation for threads, Run status, durable Run
events, SSE, and cancellation. The same-site web/API deployment and coordinated password-auth
release are complete.

### P2.2 Reminder Delivery

Status: durable in-app delivery foundation complete; user-visible inbox and external provider pending.

Completed:

- normalize fixed-duration reminder intent into a scheduled delivery time;
- synchronize create, reschedule, completion, and cancellation with a PostgreSQL outbox;
- claim due in-app reminders through the existing worker using `FOR UPDATE SKIP LOCKED`;
- persist tenant-scoped status, attempts, provider IDs, and delivery timestamps;
- expose delivery records through `GET /api/reminders`.

Remaining:

- render a minimal in-app reminder inbox;
- select one external provider suitable for target users in China;
- implement provider acknowledgement, retry scheduling, and terminal failure acceptance.

Completion means a created reminder produces one observable notification or one explicit,
recoverable failure record.

The PostgreSQL outbox, fixed-duration normalization, source replacement/cancellation rules,
tenant-scoped query API, worker claiming, and idempotent `in_app` delivery are implemented.
Remaining work is a minimal web notification surface and, after product-channel selection, one
external provider adapter with retry and acknowledgement acceptance.

### P2.3 Minimal Usable Experience

- expose tenant-scoped, cursor-paginated calendar and task query APIs (completed);
- show today, tomorrow, and open-task views using those APIs (completed);
- render created/changed objects from structured results;
- preserve structured clarification controls;
- provide clear retry behavior for provider-unavailable failures;
- connect browser recording to transcription, editable text confirmation, and normal command
  submission (implemented with selectable Cloudflare Workers AI and Alibaba Cloud adapters;
  authenticated browser acceptance with non-sensitive Chinese recordings remains).

This milestone should keep TypeScript API and feature logic reusable for the planned visual
redesign. It does not include brand polish or a large component-system migration.

## Explicitly Deferred

- multi-Agent orchestration;
- external calendar synchronization;
- organization administration and billing UI;
- multiple notification channels at once;
- native mobile applications;
- detailed visual redesign;
- per-step token cost UI.

## Immediate Next Work

1. Add release protection: production auth fail-closed, endpoint-specific limits, login abuse
   protection, and reproducible deployment checks while keeping registration open.
2. Build the minimal inspectable calendar/task experience for registered users.
3. Add Run reconnection and stable API errors so users can recover from network and provider faults.
4. Keep reminder UI and external provider work deferred until it becomes a product priority.

## Operational Acceptance

A support report must be traceable without reading private user content. API logs and durable Run
events should allow an operator to follow:

```text
request_id -> authenticated user/tenant -> thread_id -> run_id -> runtime/tool event -> object id
```

Logs record status, latency, provider request IDs when available, safe error types, and correlation
IDs. They do not record passwords, session tokens, cookies, raw audio, or full command text.
