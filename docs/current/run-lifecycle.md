# Current Run Lifecycle

This document describes the implemented command Run, live-stream, persistence, and recovery path.
The architectural rationale is recorded in
[ADR-007](../adr/007-stream-canonical-agent-messages.md).

## State Model

An Agent Run has one of these states:

```text
queued -> running -> completed
                  -> needs_clarification
                  -> failed
                  -> cancelled
queued ----------------> failed
queued ----------------> cancelled
```

`completed`, `needs_clarification`, `failed`, and `cancelled` are terminal for that Run. A
clarification response creates a follow-up Run on the same thread rather than reopening the old Run.

## Creation And Queueing

```text
POST /api/threads/{thread_id}/command-runs
  -> authenticate and resolve TenantContext
  -> validate command and Idempotency-Key
  -> persist user message and queued agent_run in PostgreSQL
  -> commit
  -> enqueue only run_id in arq/Redis
  -> return run_id immediately
```

The request does not execute the model. Queue delivery is at least once, so the worker restores the
Run from PostgreSQL and checks its state before doing work. The `run_id` is also the queue job
identity, preventing duplicate queued jobs for the same Run.

## Worker Execution

```text
arq worker receives run_id
  -> open independent database session
  -> load Run, tenant, owner, thread, and input from PostgreSQL
  -> transition queued to running atomically
  -> assemble bounded history, prompt, tools, and trusted context
  -> invoke North RunExecutor
  -> North performs the only production agent.astream loop
  -> tools commit scoped product changes
  -> lifecycle hook persists messages and final Run state
  -> settle provider usage exactly once
```

Dayboard does not call `agent.astream` directly. There is no synchronous production worker or
`stream_agent_once` path beside North `RunExecutor`.

## Live Stream

North publishes canonical model and tool chunks through its Redis `StreamBridge`. The Worker and
API construct bridge clients against the same Redis deployment.

```text
North RunExecutor
  -> canonical messages/values chunks
  -> Redis Stream keyed by Run
  -> FastAPI SSE join endpoint
  -> Dayboard safe projector
  -> browser Run reducer
```

Redis Streams are bounded, expiring, cross-process fanout. PostgreSQL remains authoritative for
Run state and conversation history.

The browser-visible event contract includes:

```text
assistant_text_delta
schedule_item_result
schedule_items_result
run_created
run_started
tool_call_started
tool_call_completed
tool_call_error
clarification_requested
run_completed
run_failed
run_cancelled
stream_replay_gap
```

The safe projector allowlists scheduling tool results and emits typed snapshots. Create and mutation
tools emit `schedule_item_result`; calendar/task searches emit one `schedule_items_result` containing
all safe matches. The browser never parses assistant prose to discover calendar entries or tasks.
It upserts result parts by schedule kind and entity ID, so an item found and then changed in the same
Run renders once with its latest snapshot. All named events pass through one state reducer.

Model and summarization lifecycle events remain in the durable RuntimeJournal for usage and audit,
but are not published through the user-facing SSE contract. Tool artifacts carry complete safe
presentation snapshots independently from compact model-visible ToolMessage content.

## Ordering And Durability

A tool's product transaction commits before its successful ToolMessage is projected. Before North
publishes the end sentinel, Dayboard lifecycle hooks persist:

- terminal Run status and result message;
- assistant conversation text;
- safe schedule result parts in `dayboard.schedule-results@1` presentation envelopes;
- clarification state when required;
- durable RuntimeJournal events used for diagnostics and usage correlation.

The Platform persists only the generic presentation kind, schema version, and opaque payload.
Dayboard validates the known payload before writing it and again when projecting history through
the public API. The complete UTC schedule snapshots used by the UI live in the presentation
payload, while compact local-time ToolMessage receipts remain model-only. Run lifecycle status is
read from the authoritative Run row and is not repeated in the presentation.

When the trailing tool-call batch contains only successful terminal schedule writes, Dayboard's
Agent middleware returns a deterministic grounded AI message and ends the loop without a final
provider confirmation call. This optimization never runs for search results, tool errors,
clarification, malformed output, partial completion, or unresolved work. The committed artifact is
still projected and persisted before the Run becomes terminal.

`agent_run_events` are durable observability records. They are not polled as the primary live UI
protocol and are not used to reconstruct schedule cards.

## Reconnection And Replay

The SSE endpoint accepts `Last-Event-ID` and subscribes through the Redis StreamBridge cursor. If the
cursor is older than retained live history, the bridge emits `stream_replay_gap`. The web client
reloads persisted conversation history and ignores late replay recovery after the Run has reached a
terminal result.

If a live terminal event is unavailable, the SSE endpoint reads the terminal Run state from
PostgreSQL and emits the appropriate terminal event. A page reload asks for the thread's active Run
and rejoins it when present.

Historical assistant messages render schedule cards from their persisted, versioned presentation.
The same typed parts are used for live SSE and refresh recovery, and a browser test verifies that
cards remain identical after reload. History does not query current business rows by
`created_by_run_id`, because those rows may have changed since the original conversation.

## Clarification

`ask_clarification` interrupts execution after Dayboard persists a structured interaction. The Run
finishes as `needs_clarification`; SSE emits the question and the typed Thread-state endpoint returns
the safe option presentation. A choice request carries the conversation-state version and stable
option key. Dayboard validates the hidden product-owned candidate, then the Platform atomically
consumes the expected Interaction version and creates the idempotent continuation Run, user message,
and `run_created` event. An identical `Idempotency-Key` retry resolves the existing Run before reading
Interaction state; a different or stale choice receives a conflict.

## Cancellation And Failure

Cancellation is explicit. Queued and running Runs transition atomically to `cancelled`. Workers
check cancellation before execution, during lifecycle boundaries, and before publishing results.

Provider, tool, queue, and unexpected runtime failures transition the Run to `failed` with a safe
user-facing result. Detailed correlation remains in structured logs and durable events without
logging credentials, cookies, raw audio, or full command text.

The worker scans stale active Runs. Queued and running Runs have separate timeout rules and
status-specific atomic failure transitions. A delayed job exits when it observes that recovery has
already made the Run terminal.

## Usage And Budgets

North normalizes usage per model call. Dayboard attributes and settles the aggregate once per
`(tenant_id, run_id)` in a separate database session, including completion, clarification, failure,
interruption, and cancellation paths. Admission currently occurs in Dayboard; migration of scoped
provider-token policy to Northgate remains future work.

Operator diagnosis follows:

```text
request_id -> tenant/user -> thread_id -> run_id -> runtime/tool event -> product object
```

Token and cache diagnostics live in [../token-usage-diagnostics.md](../token-usage-diagnostics.md).
