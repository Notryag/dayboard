# ADR-011 Use Call-Accurate Agent Activity

## Status

Accepted

## Context

Dayboard already persists North model and tool lifecycle events and streams safe tool progress to the
browser. The current web client appends every progress event to a ticker, so one tool invocation can
appear as separate “started” and “completed” messages. It also discards the activity as soon as the
Run settles.

Lexora is the second North and Agent Platform consumer. Its legal workflow adds subagents and exposed
the same correlation problem: grouping by tool name hides separate searches, while grouping every
event produces duplicate rows. DeerFlow resolves this with stable tool-call and task identities and
keeps product presentation separate from runtime data.

## Decision

North remains the source of product-neutral runtime facts:

```text
model invocation      call_id
tool invocation       call_id
subagent invocation   task_id
subagent child work   task_id + its own call_id
```

North will propagate `task_id` onto model and tool events executed inside a subagent. It will not own
Chinese labels, persistence, redaction, or visual components.

Dayboard will continue projecting North events in `dayboard.agent.observability`. The projection will
publish only allowlisted fields required by the UI: stable identity, technical operation name, safe
product summary, terminal status, and duration. Raw model output, reasoning, unrestricted inputs,
tool results, and provider errors remain excluded.

The browser will merge the start and terminal event of one invocation by `call_id`. Separate calls to
the same tool remain separate rows. The activity view is expanded during execution and on failure,
collapses after a successful answer, and can be reopened. Dayboard currently has no product subagents,
but its event parser will retain the generic `task_id` contract so future specialists do not require a
second protocol.

Lexora uses the same correlation rules while owning legal Agent names and retrieval summaries. The
applications do not share React components or product labels.

## Consequences

- Displayed tool state corresponds to a real invocation rather than event arrival order.
- Repeated searches and operations remain independently observable.
- Product-specific redaction stays close to each product's tool schemas.
- The UI may summarize model calls, but it must not invent specialist phases from timing alone.
- Existing event rows and older SSE payloads remain readable through bounded fallbacks.
- Historical per-message activity in Dayboard remains a later slice; this decision first fixes the
  active and most recently completed Run experience without changing message persistence.
