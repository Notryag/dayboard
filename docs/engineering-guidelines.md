# Engineering Guidelines

## Core Principles

- Keep dependency direction `north <- agent_platform <- dayboard`.
- Keep Dayboard product concepts out of `north` and `agent_platform`.
- Keep `north` runtime concepts out of Dayboard business models unless they are references, such as `run_id`.
- Treat PostgreSQL as the source of truth.
- Treat Redis or Valkey as infrastructure for queues, fanout, locks, rate limits, and cache.
- Make tenant and user context explicit from the first implementation.
- Prefer mature existing libraries over custom implementations for infrastructure, protocol, parsing, UI primitives, and generated clients.

## Design Durable Invariants First

Do not treat foundational data and architecture decisions as temporary implementation details.
Before coding a feature that crosses persistence or service boundaries, identify the invariants
that must remain correct as the product grows. A shortcut at this layer is expensive because the
same assumption spreads into migrations, repositories, domain models, API schemas, generated
clients, Agent tools, prompts, cached context, tests, and production data. Correcting it later is a
system-wide protocol migration rather than a local refactor.

Review these questions before the first schema or public contract is written:

1. What is the authoritative source of truth and who owns each transformation?
2. Is each field carrying exactly one semantic responsibility?
3. What are the transaction, concurrency, idempotency, and tenant-isolation guarantees?
4. Which representation belongs at the database, service, API, model, and UI boundaries?
5. Which constraints and indexes make invalid states impossible and expected access paths efficient?
6. How will the design migrate, roll back, recover, and remain observable under real concurrency?
7. Is the design extensible through stable boundaries, rather than speculative abstractions or
   compatibility branches?

Choose the strongest simple design supported by known requirements. "Extensible" does not mean
building unused generality; it means preserving clear ownership, single-purpose fields, explicit
invariants, and replaceable boundaries. Optimize foundational correctness before delivery speed,
while allowing presentation and other low-cost details to evolve incrementally.

The schedule concurrency redesign is the reference example. `updated_at` was initially reused as
an optimistic-lock token even though it is an audit field. That coupled concurrency correctness to
timestamp precision, database update behavior, timezone/serialization rules, and client round
trips. It also sent long timestamps through REST and model tool schemas. Replacing it with
`row_version` required coordinated database, repository, API, generated TypeScript, Agent receipt,
prompt, checkpoint, and test changes. A dedicated integer version from the first migration would
have been both more correct and cheaper: audit time answers when a row changed, while `row_version`
answers whether it is still the exact revision previously read.

Time representation exposed the same class of mistake. Allowing UTC entities and Beijing local
values into one model context made the model responsible for conversion and permitted an eight-hour
shift to become a false scheduling conflict. The durable design assigns one representation per
boundary: Beijing local wall-clock values for the model, timezone-aware datetimes in application
code, UTC instants in PostgreSQL, and full absolute entities only in UI artifacts. See
[current/time-protocol.md](./current/time-protocol.md).

## Documentation Boundaries

- `docs/current/` is the only canonical whole-system description. Change the relevant current
  document in the same commit as an implementation contract change.
- Keep `PROJECT_STATE.md` limited to current version, completed work, next milestone, known issues,
  and release checks. Do not append implementation chronology.
- ADR context is historical by design. Add or supersede an ADR when a costly decision changes; do
  not continuously rewrite accepted decisions to resemble current-state documentation.
- Files under `docs/archive/` never guide implementation and must identify themselves as archived.
- Specialized guides may own procedures or detailed contracts, but should link to current facts
  instead of repeating the system architecture.

## Scaffolding First

Use official or mature scaffolding when it exists.

Examples:

- create Next.js using the Next.js CLI
- create Alembic migrations using Alembic commands
- add shadcn/ui components using the shadcn CLI when selected
- generate TypeScript API clients from OpenAPI when the API stabilizes

Do not manually recreate large boilerplate that a maintained tool can generate.

Generated code may be adjusted to fit the project, but large generated artifacts should stay isolated from hand-written application code.

## Reuse Before Building

Before implementing a non-trivial feature, check in this order:

1. Python or TypeScript standard library
2. existing Dayboard code
3. existing `north` capability
4. mature open-source library
5. custom implementation

Do not duplicate existing implementations for:

- date and timezone handling
- schema validation
- database migrations
- queues and workers
- SSE clients
- OpenAPI clients
- form handling
- UI primitives
- calendar display widgets
- ASR provider clients

Adding a third-party dependency is encouraged when it reduces real implementation risk and has a clear boundary. Prefer libraries with active maintenance, clear APIs, reasonable size, and low lock-in. Stability, operability, and maintainability are more important than minimizing dependency count.

Good candidates for reuse include:

- UI primitives and component systems, such as Radix UI and shadcn/ui
- icons, such as lucide-react
- server state and caching, such as TanStack Query
- local/client state, such as Zustand or Jotai
- forms and validation adapters, such as React Hook Form and Zod
- dates, timezones, and calendar UI libraries
- tables, virtual lists, upload widgets, recorder widgets, and SSE clients
- API client generation from OpenAPI

Avoid building custom versions of these unless the product has a clear requirement that existing libraries cannot meet.

Record major dependency choices in ADRs.

Dependency rules:

- Use mature libraries freely for product delivery, but isolate them behind feature or infrastructure boundaries when practical.
- Do not let a UI library define backend contracts or domain models.
- Do not wrap every library immediately. Wrap only when it protects business code, provider choice, or generated contracts.
- Prefer CLI installation and generated setup for libraries that provide it, such as shadcn/ui.
- Check current documentation before adding a library with fast-moving setup commands or breaking changes.

## Backend Layers

Repository-level package ownership is defined by
[ADR-008](./adr/008-introduce-agent-application-platform.md): North owns runtime primitives,
`agent_platform` owns reusable application capabilities, and Dayboard owns scheduling product
semantics. The package boundary sits above the internal Dayboard backend layers below.

Target backend layout:

```text
dayboard/
  api/
  app/
  agent/
  domain/
  tools/
  db/
  workers/
  integrations/
```

Responsibilities:

- `api`: HTTP routes, SSE routes, request and response schemas
- `app`: use cases and orchestration
- `agent`: `north` integration, prompts, agent construction
- `domain`: business models, policies, validation
- `tools`: thin agent-facing adapters
- `db`: SQLAlchemy models, repositories, sessions, migrations
- `workers`: background jobs
- `integrations`: ASR, object storage, external APIs

Allowed dependency direction:

```text
api -> app -> agent/tools/domain -> db/integrations
```

Avoid:

- business rules in API routes
- raw SQL scattered outside repositories
- tool functions containing full business workflows
- `north` importing Dayboard code
- request context stored in global mutable state

## Tool Design

Agent tools should be narrow and explicit.

Prefer:

```text
create_calendar_entry
search_calendar_entries
reschedule_calendar_entry
cancel_calendar_entry
create_task_item
search_task_items
update_task_item
```

Avoid:

```text
manage_calendar(action, payload)
```

Tool functions should be thin:

```text
tool input
  -> Pydantic validation
  -> application/domain service
  -> repository
  -> structured tool result
```

The LLM response is not a source of truth. A database row created through a tool is the source of truth.

## Tenant Context

Service and tool boundaries must accept a `TenantContext` even while the product uses a shared
database deployment.

```text
TenantContext:
  tenant_id
  user_id
  timezone
  locale
  isolation_mode
```

Rules:

- `tenant_id` and `user_id` must come from trusted server context.
- The model must not generate tenant, user, permission, or run identity fields.
- Repository queries must include `tenant_id`.
- Tool input schemas must not expose trusted context fields.
- Future dedicated schema or dedicated database support should be added through a database/session resolver, not by rewriting services.

## Database Rules

- Use PostgreSQL and Alembic for product persistence.
- Use SQLAlchemy models for persistence and Pydantic models for API/tool schemas.
- Keep SQLAlchemy models separate from API response schemas.
- Use transactions for writes.
- Use soft deletion for business objects with `deleted_at`.
- Store external files in object storage; store only URIs and metadata in PostgreSQL.
- Keep migrations replayable and code-reviewed.

Common business table fields:

```text
tenant_id
created_at
updated_at
deleted_at
owner_user_id
created_by_run_id
updated_by_run_id
```

Time rules:

- Agent-facing scheduling tools accept local date/time values without `Z` or a numeric offset.
- Resolve local values at the Dayboard boundary using the trusted `TenantContext.timezone`; never
  accept timezone ownership from model or per-command browser input.
- Use timezone-aware datetimes after that boundary.
- Store canonical timestamps in PostgreSQL as timezone-aware values.
- Store the trusted product/tenant IANA timezone separately, such as `Asia/Shanghai`.
- Natural-language time parsing must use an explicit reference time and timezone.

## API Rules

- Use Pydantic request and response schemas.
- Do not return raw SQLAlchemy models.
- Use stable error envelopes.
- Long-running agent work should use `agent_runs` and background workers.
- Use `Idempotency-Key` for command creation and other retryable write endpoints.
- Expose run status through `GET /api/runs/{run_id}`.
- Expose live run updates through SSE when streaming is implemented.
- Apply rate limiting at the API boundary for user-facing write and command endpoints.
- Use Redis or Valkey for shared rate limit state in server environments.
- Do not rely only on frontend throttling for cost or abuse control.
- Never use a caller-supplied tenant or user header as a rate-limit or authorization identity.
- Give every HTTP request a validated or generated request ID and return it in `X-Request-ID`.
- Bind authenticated user and tenant IDs to structured request logs after session resolution.
- Correlate queued Agent work with thread and Run IDs; durable Run events remain the user-visible
  execution record while logs are the operator diagnostic record.
- Never log passwords, password hashes, raw session tokens, cookies, authorization headers, raw
  audio, or full command text.

Suggested error shape:

```json
{
  "error": {
    "code": "missing_required_field",
    "message": "A start time is required.",
    "request_id": "req_..."
  }
}
```

## Agent And LLM Rules

- Tools create and mutate data; plain model text does not.
- Tool schemas should be narrow, typed, and clear.
- Missing required scheduling fields should trigger clarification instead of unsafe guessing.
- Business rules belong in code, not only in prompts.
- Prompts should explain how to use tools and when to clarify.
- Tool results should be structured and UI-friendly.
- Model/provider-specific code should stay behind `north` or an integration boundary.
- Log run metadata, tool names, tool arguments, results, object ids, errors, and latency.
- Do not log secrets, raw provider tokens, or unnecessary sensitive audio payloads.
- Protect trusted context from prompt injection. User text cannot override tenant, user, permission, or system context.
- Load model credentials and gateway URLs only from environment variables or secret stores.
- Do not commit real `OPENAI_API_KEY`, `OPENAI_BASE_URL`, provider keys, or copied local Codex credentials.
- Support OpenAI-compatible forwarding through `.env` variables such as `OPENAI_BASE_URL` and `OPENAI_API_KEY`.
- Add provider-level request/token budgets before enabling real LLM command execution.

Good tool result shape:

```json
{
  "type": "calendar_entry_created",
  "calendar_entry": {
    "id": "cal_...",
    "title": "Product review",
    "start_time": "2026-07-22T15:00:00+08:00",
    "updated_at": "2026-07-20T09:00:00Z"
  },
  "conflicts": []
}
```

## Frontend Rules

Use Next.js, React, and TypeScript for the first UI.

Suggested layout:

```text
app/
components/
features/
lib/api/
lib/types/
```

Rules:

- Pages compose data and layout.
- Complex UI belongs in feature components.
- Data fetching belongs in API/client helpers or route-level loaders.
- Do not spread raw fetch logic across components.
- Do not duplicate API types by hand once OpenAPI generation is available.
- Keep time display behind shared formatting helpers.
- Keep components mobile-aware while treating the responsive web application as the current client.
- The first page should be a mobile-first conversation surface: message history on top, text input and voice action at the bottom.
- shadcn/ui is an acceptable first component system because it gives editable local components on top of Radix primitives.
- Use lucide-react icons where available instead of hand-drawn SVG icons.
- Put theme decisions in CSS variables or shadcn theme tokens before styling feature components.
- Avoid hard-coded brand colors, spacing, shadows, or radii inside React components.
- Use a focused state tool when state becomes shared across distant components. Prefer simple React state for local UI, TanStack Query for server state, and Zustand or Jotai for cross-component client state.
- Keep agent run state and persisted schedule data server-backed. Frontend state should not become a second source of truth.

React files can be larger than backend files when they represent cohesive UI. A page or complex component around 400-500 lines is acceptable if it has one clear responsibility.

Evaluate splitting when:

- a React file exceeds 500 lines
- one file mixes API calls, complex state, business rules, and layout
- a hook exceeds 150 lines
- a component has multiple unrelated interaction modes
- a test setup becomes hard because too many concerns are coupled

## File Size And Decomposition

Use these as review triggers, not hard failures.

Python:

- file over 300 lines: evaluate splitting
- function over 50 lines: evaluate splitting
- service with many public methods: consider use-case-specific services

TypeScript/React:

- file over 500 lines: evaluate splitting
- hook over 150 lines: evaluate splitting
- generated client files may exceed these limits if isolated

Split by responsibility, not by arbitrary line count.

## Testing Strategy

Add focused tests when they protect important behavior, but do not routinely execute tests
after ordinary small changes. Test execution consumes time and infrastructure and should be
reserved for meaningful verification points.

Run tests at key moments:

- shared runtime, database schema, concurrency, idempotency, or cross-module contract changes;
- production incident fixes and other regression-prone reliability work;
- completion of a substantial feature slice;
- before a release, deployment batch, or merge that changes production behavior;
- when static inspection cannot establish correctness.

For small documentation, copy, styling, or narrowly mechanical code changes, default to diff
review and relevant static checks only. Do not run a test suite merely because files changed.
When tests are warranted, run the smallest affected set first; full regression and live-model
tests are reserved for release-level or broad/high-risk changes.

Use slice-based test design, and do not require strict test-first development for every small piece.

Default rhythm:

```text
design a small vertical slice
  -> implement domain/schema/service code
  -> add deterministic tests for that slice
  -> add API/tool tests when the boundary exists
  -> add a small number of agent-flow tests after tool behavior is stable
```

Priority order:

1. domain and policy unit tests
2. repository tests against PostgreSQL
3. deterministic tool tests without LLM calls
4. API tests
5. worker/run status tests
6. a small number of agent flow tests
7. frontend interaction tests for key flows

LLM-dependent tests should be limited and optional in normal local runs. Most correctness should be covered without calling a model.

The browser release gate uses Playwright for the critical user journeys: authentication and Thread
creation, multi-item SSE rendering, refresh and active-Run recovery, optimistic edit plus undo, and
clarification resume. Browser tests run the real Next.js UI against a deterministic stateful API
and SSE contract fixture. Voice interaction uses fixed audio bytes through a test MediaRecorder;
it must not require microphone hardware or permission. Real backend semantics remain covered by
PostgreSQL API/service tests, while live model quality is measured by Agent Eval.

FastAPI OpenAPI is the HTTP schema source of truth. CI exports it from the API job and checks the
committed `schema.d.ts` in the Web job. Use `openapi-fetch` for typed endpoints and TanStack Query
for server-backed query state; do not rebuild endpoint parameter types or pagination caches with
component-local state. SSE is not an OpenAPI request/response shape, so validate its JSON at the
transport boundary and reduce only the resulting discriminated `RunEvent` union.

Unit tests for application orchestration may use fakes for database sessions, model invokers, and provider gateways when the behavior under test is routing, budgeting, logging, or status mapping. Repository tests, API persistence tests, and tool tests must still run against PostgreSQL because PostgreSQL is the source of truth and its constraints, JSONB behavior, timestamps, and transaction behavior are part of the product contract.

For Dayboard, verify completed substantial slices before moving far ahead; do not turn
every incremental edit into a test execution checkpoint.

## Dependency Decisions

Use ADRs for decisions that shape the project long-term:

- framework choice
- database choice
- queue choice
- UI system choice
- ASR provider choice
- auth provider choice
- calendar component choice
- significant `north` integration decisions

Small implementation dependencies can be documented in the PR or commit message instead of a full ADR.
