# ADR-002 Adopt DeerFlow Runtime Observability Boundaries

## Status

Accepted

The temporary decision to tail PostgreSQL for live delivery is superseded by ADR-007. The
RuntimeJournal observability boundary remains accepted.

## Context

Dayboard initially emitted progress text directly from scheduling tools. This made the
first SSE experience visible, but it could not explain model calls, correlate tool input
with output, report latency, or scale to new tools without adding more product-specific
instrumentation.

DeerFlow separates two related concerns:

1. LangGraph stream modes are bridged to a live per-run stream for immediate delivery,
   heartbeats, and reconnection.
2. A callback-based RunJournal normalizes model, tool, message, usage, and lifecycle data
   into a durable event store for history and audit.

Its frontend reconstructs reasoning and tool steps from structured AI and Tool messages
using tool call IDs. DeerFlow also keeps the Gateway, persistence, and UI outside its
reusable agent harness.

Dayboard needs the same boundaries, but not DeerFlow's complete Gateway, sandbox,
subagent, artifact, or administration surface.

## Decision

Adopt the following design:

- `north.RuntimeJournal` translates LangChain callbacks into product-neutral runtime
  events.
- `north.RuntimeEventSink` is the only integration boundary required by a product.
- Model and tool events use call IDs so starts and terminal outcomes can be correlated.
- `north` does not choose persistence, tenant policy, SSE endpoints, or user-facing text.
- Dayboard projects runtime events through an allowlist, persists them in PostgreSQL, and
  serves them through its existing Run SSE endpoint.
- Product events such as conflict checks may remain explicit when they describe behavior
  that generic model/tool callbacks cannot express.
- Live delivery and durable history remain separate concepts even while Dayboard's first
  implementation tails PostgreSQL for both.

Initial normalized events are:

```text
model.started
model.completed
model.error
tool.started
tool.completed
tool.error
```

Dayboard maps these to product-facing events such as `agent_model_started` and
`tool_call_started`.

## Security And Presentation

- Never persist or display system prompts, credentials, database URLs, hidden tenant
  context, or unrestricted tool output.
- Tool inputs are allowlisted by tool name before persistence.
- Model response bodies and raw provider reasoning are not persisted in Dayboard progress
  events.
- Provider-supplied reasoning can be supported later only through an explicit, separately
  reviewed presentation policy. Dayboard must not synthesize or request hidden chain of
  thought for observability.
- User-facing progress describes verifiable state and actions, not unverifiable internal
  thought.

## Consequences

Dayboard can show which operation is running, its safe arguments, outcome, latency, and
model usage without modifying every tool. Historical events remain replayable after
disconnects and process restarts.

The product adapter must be maintained whenever a new tool is introduced. Unknown tools
receive generic text and no input fields until explicitly allowlisted. ADR-007 adds a Redis
Stream for live canonical messages while PostgreSQL remains the durable source of truth.
