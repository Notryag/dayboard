# ADR-007 Stream Canonical Agent Messages

## Status

Accepted

## Context

Dayboard currently tails `agent_run_events` from PostgreSQL and uses those observability records as
its live UI protocol. The events describe lifecycle and progress, but discard canonical AI and tool
messages. When a Run finishes, the web client queries `/api/schedule-items/by-runs` and infers chat
cards from business rows whose `created_by_run_id` matches the Run.

That design has four problems:

- a tool result cannot render when it arrives;
- model output is delivered only when the Run reaches a terminal state;
- updated and cancelled objects cannot be reconstructed reliably from `created_by_run_id`;
- observability events, product presentation, and business persistence are conflated.

DeerFlow uses a different boundary. The graph emits canonical `values`, `messages`, and `custom`
chunks. A stream bridge transports those chunks to clients, and the frontend reduces AI message
chunks and ToolMessages into UI. Its durable journal is an observability concern, not the primary
presentation protocol.

Dayboard is still in development. There is no released client contract to preserve, so the old
`/api/schedule-items/by-runs` inference path will be removed instead of retained as compatibility.

## Decision

Adopt a canonical message stream with explicit North and Dayboard ownership.

### North owns

- the only production `agent.astream` loop, implemented by an asynchronous Run executor;
- Run execution ordering: metadata, canonical chunks, lifecycle finalization, error, and end;
- normalizing graph stream modes into `RuntimeStreamEvent`;
- preserving serialized message data, stream mode, namespace, message IDs, and tool call IDs;
- an asynchronous `StreamBridge` contract with replay cursors, heartbeat and end sentinels;
- product-neutral in-memory and Redis Stream bridge implementations;
- publishing canonical chunks directly from the Run executor to the StreamBridge;
- returning the latest `values` state to callers after the stream ends.

North must not know about tasks, calendar entries, tenants, FastAPI, Redis deployment, or Dayboard
presentation schemas.

### Dayboard owns

- selecting the North stream modes used by the product;
- projecting canonical ToolMessages through a strict per-tool allowlist;
- presenting scheduling ToolMessages only from the root graph namespace unless a future ADR
  explicitly trusts a named subgraph;
- mapping safe scheduling tool results to typed conversation parts;
- tenant and owner authorization;
- PostgreSQL business writes and conversation history;
- selecting and configuring North's Redis-backed live fanout;
- lifecycle hooks that persist Dayboard Run status, conversation messages, and product state before
  North publishes the end sentinel;
- SSE framing, reconnect cursors, heartbeats, and terminal Run semantics;
- the frontend reducer and rendering of text and schedule parts.

The live path is:

```text
North async RunExecutor
  -> agent.astream(values, messages)
  -> North StreamBridge.publish(canonical mode)
  -> Dayboard safe message projector
  -> Dayboard SSE join endpoint
  -> web Run reducer
  -> assistant text and schedule cards
```

The recovery path is:

```text
safe projected tool parts collected during Run
  -> assistant conversation message metadata
  -> PostgreSQL conversation history
  -> web message renderer
```

Tool writes commit before their ToolMessage can be treated as a successful product result. The
ToolMessage is presentation data, not the authority that creates or mutates a schedule object.

## Stream Contract

North emits product-neutral events:

```text
RuntimeStreamEvent:
  mode: values | messages | custom
  namespace: tuple[str, ...]
  data: JSON-compatible serialized graph chunk
```

The transport contract is:

```text
StreamBridge:
  publish(run_id, event, data, namespace)
  publish_end(run_id)
  subscribe(run_id, last_event_id, heartbeat_interval)
  cleanup(run_id)
```

Dayboard exposes only projected events to the browser:

```text
assistant_text_delta:
  message_id
  delta

schedule_item_result:
  tool_call_id
  operation
  item: { kind: calendar | task, value: safe product snapshot }

run_completed | clarification_requested | run_failed | run_cancelled
```

The browser never parses natural-language model content to discover product objects. It keys tool
results by `tool_call_id` and deduplicates retransmitted stream entries. Final assistant text is a
separate message from schedule result cards.

## Persistence And Reconnection

- PostgreSQL remains the source of truth for Runs, conversations, tasks, and calendar entries.
- Redis Streams provide live cross-process fanout and bounded replay, not product truth.
- The SSE join endpoint uses the standard `Last-Event-ID` cursor and resumes through the Bridge.
- If a cursor predates Redis retention, the Bridge emits an explicit replay-gap signal before
  replaying the earliest retained event; the gap is never treated as a complete replay.
- On expired live history or after a terminal Run, the client reloads canonical conversation
  history from PostgreSQL.
- Assistant conversation message metadata stores safe projected parts so historical cards do not
  require querying business objects by Run ID.
- RuntimeJournal events remain in `agent_run_events` for audit, progress, usage, and diagnostics.
  They are not parsed as canonical messages.

## Removal

The migration removes:

- `GET /api/schedule-items/by-runs`;
- `RunScheduleItemGroup` and the frontend batch-fetch effect;
- product event labels such as `calendar_entry_created` and `task_item_created` from the generic
  progress parser;
- the assumption that `tool_call_completed` contains enough data to render a product result.

## Prohibited Shortcuts

The following are architectural violations, even when they reduce implementation work:

- a Dayboard service calling `agent.astream` directly;
- a helper such as `stream_agent_once` that returns streamed chunks through a callback while
  bypassing RunExecutor and StreamBridge;
- using a stream sink callback as the primary live transport;
- maintaining synchronous and asynchronous production Run workers in parallel;
- publishing an end sentinel before Dayboard's lifecycle hook has durably finalized the Run;
- polling `agent_run_events` as a substitute for the live StreamBridge;
- adding compatibility paths for unreleased development contracts instead of removing them.

Code review and tests must enforce one production execution path:

```text
Dayboard Worker -> North RunExecutor -> North StreamBridge -> Dayboard SSE
```

## Implementation Map

North implementation:

- `north/runtime/worker.py`: `RunExecutor`, lifecycle ordering, canonical mode publication;
- `north/runtime/stream_bridge/base.py`: asynchronous transport contract and sentinels;
- `north/runtime/stream_bridge/memory.py`: in-process replay for SDK use and tests;
- `north/runtime/stream_bridge/redis.py`: cross-process Redis Streams transport;
- `north/runtime/service.py`: async Run orchestration using the same executor;
- `north/client.py`: synchronous SDK adapter over the async runtime, not a second worker.

Dayboard implementation:

- `dayboard/workers/commands.py`: constructs the North Redis bridge for the Worker;
- `dayboard/app/commands.py`: supplies product lifecycle hooks and persists safe parts;
- `dayboard/agent/presentation.py`: allowlisted canonical message projection;
- `dayboard/main.py`: constructs the same North Redis bridge for the API process;
- `dayboard/api/routes.py`: authorization, bridge subscription, projection and SSE framing;
- `apps/web/src/app/page.tsx`: Run event reduction and browser reconnection behavior;
- `apps/web/src/features/chat/ChatMessageList.tsx`: text and schedule part rendering.

## Consequences

Schedule cards and model text can render incrementally, reconnect has an explicit protocol, and
historical chat rendering no longer depends on reverse queries against mutable business rows.

The implementation is larger than polling one PostgreSQL table. It requires a Redis stream adapter,
a safe projection layer, persisted conversation parts, and a frontend reducer. These boundaries are
deliberate because they keep live transport, observability, history, and business state distinct.
