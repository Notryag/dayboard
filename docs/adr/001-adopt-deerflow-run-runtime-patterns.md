# ADR-001 Adopt DeerFlow Run and Runtime Patterns

## Status

Accepted

## Context

Dayboard began with a synchronous command endpoint and a small `north` harness. That design was intentional for the first implementation slices: it kept the scheduling tools, PostgreSQL persistence, tenant context, and model boundary easy to verify before long-running execution existed.

The original design stopped being a good fit once Dayboard needed background execution, reconnectable event streams, cancellation, durable usage records, and multiple clients following the same run. Keeping synchronous and asynchronous command paths would duplicate interpretation and lifecycle behavior.

DeerFlow already addresses these runtime concerns at a larger scale. Its useful design properties include:

- threads and runs are explicit resources rather than HTTP request implementation details
- creating, streaming, joining, waiting for, and cancelling runs are distinct operations
- run management, persisted event history, and live stream fanout have separate responsibilities
- model construction is configuration-driven and supports provider-specific adapters
- middleware supports the same behavior on synchronous and asynchronous graph paths
- the Gateway owns HTTP, authentication, and task lifetime while the harness remains reusable

DeerFlow is a general agent platform, while Dayboard is a scheduling product. Copying the complete DeerFlow Gateway would introduce unrelated sandbox, MCP, artifact, channel, and administration complexity.

## Decision

Use `/root/deer-flow` as the primary reference for evolving `north` and Dayboard's run lifecycle.

Adopt these principles:

1. A command creates and commits a queued run before execution starts.
2. Background execution uses an independent database session.
3. PostgreSQL run records and events remain the recoverable source of truth.
4. Live streams are projections of the run lifecycle, not the only copy of events.
5. Run creation, stream/join, wait, cancellation, messages, and event history have explicit contracts.
6. Natural-language interpretation has one production path through `north`.
7. `north` owns reusable model factories, provider adapters, middleware contracts, run primitives, and stream abstractions.
8. Dayboard owns FastAPI routes, tenant and authorization policy, PostgreSQL product persistence, provider budgets, and scheduling tools.
9. North's asynchronous Run executor is the only production owner of `agent.astream`; products
   must not bypass it with direct invocation or callback-only streaming helpers.

Do not adopt DeerFlow application features merely because they exist. A DeerFlow component is moved into `north` only when it is product-neutral and needed by a concrete Dayboard runtime requirement.

## Enforcement

- API tests must assert that run creation returns before execution and that persisted events can be replayed.
- Boundary tests must prevent `north` from importing Dayboard or its product schemas.
- Middleware that wraps tool execution must test asynchronous behavior.
- There must be no parallel synchronous command interpretation endpoint.
- Architecture changes that diverge from this lifecycle require a new ADR that supersedes this one.

## Consequences

The API becomes easier to reconnect to, observe, cancel, and move across worker processes. The web client can follow one stable run resource rather than keeping an HTTP request open for model execution. Provider and middleware behavior can improve in `north` without leaking Dayboard concepts into it.

The design requires explicit task lifecycle management, idempotency, cancellation semantics, and a durable queue. Dayboard uses arq with Redis and treats delivery as at least once: the run id is the unique job id, workers re-check PostgreSQL state, and product tools must remain transactionally safe to retry. Operational stale-running recovery is still required for workers terminated between the running transition and terminal commit.
