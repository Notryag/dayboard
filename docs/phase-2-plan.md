# Phase 2 Plan: Usable Account Beta

## Product Goal

Move Dayboard from a shared-user technical MVP to a private beta where each real user can
safely manage their own schedules and receive useful reminders.

Phase 1 proved the Agent loop. Phase 2 is not primarily an Agent-capability phase. It closes
the product boundaries required for real use: identity, ownership, personal settings, reminder
delivery, and a minimal inspectable experience.

## Current Product Assessment

The natural-language scheduling backend is an MVP-quality closed loop:

- create, find, change, complete, and cancel calendar entries and tasks;
- execute multiple instructions from one message;
- clarify ambiguous targets with structured choices;
- persist conversations and bounded Agent context;
- expose durable Run progress and safe tool observability;
- protect writes with tenant scoping, idempotency, optimistic concurrency, and audit fields;
- run API, worker, PostgreSQL, Redis, migrations, usage accounting, and budgets in production.

The product is not ready for external users because the deployed API still resolves every
request to one development tenant/user. Password authentication and an in-app reminder outbox are
implemented but not deployed as one coordinated release. The web experience remains a prototype,
the reminder inbox is not rendered, and browser voice capture is not connected.

## Milestone Order

### P2.1 Real Identity And Ownership

Status: backend, web session flow, and isolation acceptance complete; production enablement pending.

Completed:

- username/password registration and login in FastAPI;
- Argon2id password hashes and revocable server-side sessions in `HttpOnly` cookies;
- Dayboard users, memberships, timezone/locale profiles, and an external-identity extension point;
- trusted `TenantContext` resolution from sessions and memberships;
- minimal web registration, login, logout, session recovery, and credentialed SSE;
- two-user ownership acceptance for threads and Run status, events, streaming, and cancellation.

Remaining:

- configure a same-site web/API domain;
- apply account migrations and switch production to `password` mode in the same release;
- complete external-beta ownership acceptance for calendar entries, tasks, transcripts, and usage.

Completion means two users cannot read, mutate, stream, or infer each other's data, and a
production deployment cannot start in development-auth mode by accident.

Backend acceptance now covers password-session isolation for threads, Run status, durable Run
events, SSE, and cancellation. Production enablement still requires a same-site web/API domain
and one coordinated web, migration, and auth-mode release.

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

- show today, tomorrow, and open-task views;
- render created/changed objects from structured results;
- preserve structured clarification controls;
- provide clear retry behavior for provider-unavailable failures;
- connect browser recording to transcription, editable text confirmation, and normal command
  submission when ASR credentials and sample audio are available.

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

1. Configure a same-site web/API domain and release the account migration, web login flow, and
   `DAYBOARD_AUTH_MODE=password` switch together.
2. Render delivered in-app reminders through the existing tenant-scoped API.
3. Select one China-reliable external notification provider and add acknowledgement-based retry.

## Operational Acceptance

A support report must be traceable without reading private user content. API logs and durable Run
events should allow an operator to follow:

```text
request_id -> authenticated user/tenant -> thread_id -> run_id -> runtime/tool event -> object id
```

Logs record status, latency, provider request IDs when available, safe error types, and correlation
IDs. They do not record passwords, session tokens, cookies, raw audio, or full command text.
