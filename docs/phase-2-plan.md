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
request to one development tenant/user. Reminder intent is stored but no notification is sent.
The web experience remains a prototype and browser voice capture is not connected.

## Milestone Order

### P2.1 Real Identity And Ownership

- implement username/password registration and login in FastAPI;
- hash passwords with Argon2id and use revocable server-side sessions in `HttpOnly` cookies;
- map authenticated sessions to Dayboard users and tenant membership;
- retain external identity records as the extension point for future WeChat or OIDC login;
- derive `TenantContext` only from trusted identity and membership data;
- store per-user timezone and locale;
- enforce ownership on threads, Runs, calendar entries, tasks, voice transcripts, and usage;
- remove the fixed development identity from production mode;
- add a minimal login/logout/session flow to the web app.

Completion means two users cannot read, mutate, stream, or infer each other's data, and a
production deployment cannot start in development-auth mode by accident.

### P2.2 Reminder Delivery

- normalize stored reminder intent into a scheduled delivery time;
- enqueue due reminders through the existing worker infrastructure;
- implement one notification channel suitable for the first target users;
- persist delivery status, attempts, provider IDs, and terminal failure;
- make retries idempotent and timezone-safe;
- expose sent/failed reminder state without claiming delivery before provider acknowledgement.

Completion means a created reminder produces one observable notification or one explicit,
recoverable failure record.

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

## Immediate Next Decision

Implement the FastAPI account/session boundary and request correlation, then connect the minimal
web login flow before enabling password mode in production. Do not deploy the backend mode switch
alone because the existing web client has no login surface yet.

## Operational Acceptance

A support report must be traceable without reading private user content. API logs and durable Run
events should allow an operator to follow:

```text
request_id -> authenticated user/tenant -> thread_id -> run_id -> runtime/tool event -> object id
```

Logs record status, latency, provider request IDs when available, safe error types, and correlation
IDs. They do not record passwords, session tokens, cookies, raw audio, or full command text.
