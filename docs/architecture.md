# Architecture

## Layering

Dayboard should follow this direction:

```text
Next.js web app
  -> Dayboard HTTP API / SSE API
  -> Dayboard application services
  -> north runtime: agent loop, tool execution, thread state, runtime events
  -> Dayboard tools
  -> Dayboard domain services
  -> repositories
  -> PostgreSQL
```

Supporting infrastructure:

```text
Redis or Valkey
  -> job queue
  -> run stream fanout
  -> short-lived locks and rate limits

S3-compatible object storage
  -> voice audio
  -> future attachments
```

## Responsibility Split

### Dayboard

- Next.js web app
- API and SSE endpoints
- product-specific configuration
- tenant and user context
- calendar and task schemas
- `CalendarEntry` and `TaskItem` storage
- scheduling tools
- clarification policy for schedule creation
- voice upload and ASR provider integration
- UI-facing response shaping

### North

- reusable agent runtime
- agent creation
- streamed runtime execution
- reusable tool and skill infrastructure
- thread state and artifact protocols
- runtime events such as `StreamEvent` and `RunEvent`

### Model Providers

- LLM APIs used by `north`
- later ASR APIs used by Dayboard input services

## Technology Choices

- Frontend: Next.js, React, TypeScript
- UI primitives/components: shadcn/ui on Radix UI as the first candidate
- Frontend server state: TanStack Query as the first candidate when API usage grows
- Frontend shared client state: Zustand or Jotai when local React state is insufficient
- Icons: lucide-react
- Backend: FastAPI, Pydantic, SQLAlchemy 2.x, Alembic
- Agent runtime: local `north` package dependency
- Database: PostgreSQL
- Queue/cache/stream fanout: Redis or Valkey
- Worker: async Python worker, with `arq` as the first implementation candidate
- API contract: OpenAPI generated from FastAPI, then consumed by the web app
- Object storage: S3-compatible storage for audio and future attachments
- Observability: structured logs first, OpenTelemetry later

## Project Shape

The target repository layout should keep product code, frontend code, and shared generated clients separate:

```text
dayboard/
  apps/
    api/
      dayboard/
        api/
        app/
        agent/
        domain/
        tools/
        db/
        workers/
        integrations/
    web/
      app/
      components/
      features/
      lib/
  packages/
    client/
    schemas/
  docs/
```

Backend package responsibilities:

- `dayboard.api`: HTTP routes, SSE routes, request/response schemas
- `dayboard.app`: application services and use cases
- `dayboard.agent`: `build_dayboard_agent` and north integration
- `dayboard.domain`: `CalendarEntry`, `TaskItem`, policies, validation
- `dayboard.tools`: tools exposed to the agent
- `dayboard.db`: SQLAlchemy models, repositories, sessions, migrations
- `dayboard.workers`: agent run jobs and future ASR jobs
- `dayboard.integrations`: ASR, object storage, external calendar sync later

## Network To Database Flow

Text command flow:

```text
Client
  -> POST /api/commands
  -> API validates request and resolves TenantContext
  -> application service creates agent_run
  -> job is enqueued
  -> worker runs north agent
  -> north calls Dayboard tools
  -> tool calls Dayboard domain service
  -> repository writes PostgreSQL
  -> worker records run status and runtime events
  -> client reads result or subscribes to run stream
```

Clarification flow:

```text
user text
  -> agent detects missing required scheduling data
  -> ask_clarification tool interrupts the run
  -> agent_run status becomes needs_clarification
  -> API returns the question
  -> user answers on the same thread
  -> worker resumes the agent run
```

Voice flow:

```text
Client audio upload
  -> object storage
  -> transcription job
  -> ASR provider
  -> voice_transcripts row
  -> command flow using transcript text
```

Phase 1 can skip full voice execution, but the boundary should exist.

## API Surface

Phase 1 API:

```text
POST /api/commands
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/calendar-entries
GET  /api/task-items
```

Later API:

```text
POST /api/voice/uploads
GET  /api/voice/transcripts/{transcript_id}
POST /api/calendar-entries
PATCH /api/calendar-entries/{entry_id}
DELETE /api/calendar-entries/{entry_id}
POST /api/task-items
PATCH /api/task-items/{task_id}
DELETE /api/task-items/{task_id}
```

`POST /api/commands` should support idempotent retries with an `Idempotency-Key` header.

## Agent Assembly Boundary

Dayboard owns the product assembly function. `north` should expose generic runtime primitives, while Dayboard decides which tools, prompts, context, and clarification rules are installed.

The first implementation should look conceptually like:

```python
build_dayboard_agent(
    tenant_context=tenant_context,
    tools=[
        create_calendar_entry,
        create_task_item,
        list_calendar_entries,
        list_task_items,
    ],
    prompts=dayboard_prompts,
    checkpointer=checkpointer,
)
```

This keeps product behavior in Dayboard and avoids adding Dayboard-specific assumptions to `north`.

The model must not generate trusted context fields. The server injects them:

- `tenant_id`
- `user_id`
- `timezone`
- `locale`
- `run_id`
- `thread_id`
- `request_id`

## Product Tools

Initial tools:

- `create_calendar_entry`
- `list_calendar_entries`
- `create_task_item`
- `list_task_items`

Later tools:

- `update_calendar_entry`
- `delete_calendar_entry`
- `update_task_item`
- `delete_task_item`

These tools live in Dayboard unless they prove broadly reusable across products.

## Create Calendar Entry Flow

Creating a calendar entry should call a Dayboard tool directly. There is no intermediate `north` business event.

```text
user text
  -> north agent reads tool schemas
  -> agent calls create_calendar_entry when fields are available
  -> agent asks clarification when required fields are missing
  -> create_calendar_entry validates input
  -> CalendarService creates CalendarEntry
  -> CalendarRepository writes PostgreSQL
  -> tool returns created entry id and display summary
```

Example:

```text
Input: Next Wednesday at 3pm, schedule a product review with Alice and remind me one day before.

Tool call:
  create_calendar_entry(
    title="product review",
    start_time="...",
    timezone="Asia/Shanghai",
    participants=["Alice"],
    reminder={"offset": "P1D", "anchor": "start_time"}
  )
```

If the user says "Schedule a product review with Alice", Dayboard should ask for the missing time before calling `create_calendar_entry`.

## Data Ownership

`north` runtime data:

- thread state
- runtime stream events
- run events
- tool call traces
- artifacts

Dayboard business data:

- calendar entries
- task items
- reminders
- voice transcripts
- user settings
- audit logs

`CalendarEntry` should never be added to `north` state as a core runtime concept. A tool result may reference a `calendar_entry_id`.

## Database Model

PostgreSQL is the source of truth. Redis or Valkey is not a source of truth.

Core tables:

```text
tenants
users
tenant_memberships
user_settings
calendar_entries
task_items
agent_threads
agent_runs
agent_run_events
voice_transcripts
audit_logs
idempotency_keys
```

Phase 1 can use a single development tenant, but the schema should include `tenant_id` from the start.

Required common fields:

```text
tenant_id
created_at
updated_at
deleted_at
```

Business tables should also include:

```text
owner_user_id
created_by_run_id
updated_by_run_id
```

Useful initial indexes:

```text
calendar_entries(tenant_id, owner_user_id, start_time)
calendar_entries(tenant_id, start_time)
calendar_entries(tenant_id, created_by_run_id)
task_items(tenant_id, owner_user_id, status, due_at)
agent_runs(tenant_id, thread_id, created_at)
agent_run_events(tenant_id, run_id, seq)
idempotency_keys(tenant_id, key)
```

## Tenant Extensibility

Phase 1 does not need full tenant administration or dedicated databases, but the code should pass a `TenantContext` through services and tools.

```text
TenantContext:
  tenant_id
  user_id
  timezone
  locale
  isolation_mode
```

Default mode:

```text
isolation_mode = shared
database = main PostgreSQL
queries include tenant_id
```

Future enterprise modes:

```text
isolation_mode = dedicated_schema
isolation_mode = dedicated_database
isolation_mode = dedicated_cluster
```

Keep `tenant_id` in tables even when a future tenant uses a dedicated database. It makes migrations, exports, audit, and mixed deployments simpler.

## Concurrency And Reliability

- API requests should create durable `agent_runs` before background execution starts.
- Agent execution should happen in workers, not inside long blocking HTTP requests.
- Tool writes should be transactional.
- Command creation should support idempotency keys.
- Run status should be explicit: `queued`, `running`, `needs_clarification`, `completed`, `failed`, `cancelled`.
- Long-running run output should be delivered over SSE and recoverable from persisted run events.
- Redis or Valkey can provide queueing, fanout, locks, and rate limits, but PostgreSQL remains the durable source.

## Integration Principle

Dayboard should inject its own:

- tenant context
- data stores
- default prompts
- scheduling tools
- clarification rules

It should not fork the `north` runtime unless a reusable capability is missing.
