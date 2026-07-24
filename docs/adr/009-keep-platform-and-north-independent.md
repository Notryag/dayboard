# ADR-009 Keep Platform And North Independent

## Status

Accepted

## Context

ADR-008 introduced `agent_platform` for application lifecycle capabilities that do not belong to a
scheduling product or the Agent runtime. Its original dependency diagram described a strict chain:
`Dayboard -> agent_platform -> North`.

The implemented Run boundary proves that this link is unnecessary and harmful. North already owns
the Agent loop, model invocation, LangGraph checkpointing, and runtime streaming. Agent Platform
owns durable tenant-scoped Conversation, Run, idempotency, envelope, and interaction lifecycle.
The Platform does not need a North import to express those rules; Dayboard supplies a
`RunExecutionDriver` that bridges the two packages.

Forcing Platform to import North only to preserve a visual three-layer stack would duplicate runtime
concepts in application code and make every future consumer adopt North even when its runtime needs
differ.

## Decision

Keep North and Agent Platform as independent lower-level dependencies:

```text
Dayboard ------> agent_platform
   |
   +-----------> North

future product -> agent_platform
future product -> its chosen runtime
```

Dayboard's composition root creates the product-owned adapter implementing Platform's
`RunExecutionDriver` port. North and Platform do not import each other. North graph state is
temporary runtime state; Platform's PostgreSQL-backed Conversation and `PendingInteraction` state
is the durable application authority.

An optional North adapter package is permitted only if a second product proves a stable,
product-neutral integration contract. It must depend inward on Platform ports and must not change
the framework-free Core or Application packages.

## Consequences

- Platform remains small and only depends on Pydantic today.
- North continues to evolve its runtime, checkpoint, stream, and compaction APIs without being
  coupled to tenant persistence or product semantics.
- Products own the explicit bridge and can choose another runtime without replacing their durable
  Conversation/Run lifecycle.
- PostgreSQL adapters remain Dayboard-owned until a second product proves a shared persistence
  schema and transaction contract.
- The clarification bridge must converge North's temporary signal into one Platform outcome; it
  must not create a second durable interaction authority.
