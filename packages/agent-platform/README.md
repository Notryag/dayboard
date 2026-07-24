# Agent Application Platform

`agent_platform` is the reusable application-lifecycle layer used alongside North by products such
as Dayboard.

The first extraction slice provides the trusted `TenantContext`, product-neutral Conversation and
Run contracts, persistence ports, and storage-independent Conversation and Run services. Dayboard
imports these directly; its former duplicate domain and service modules have been removed. Dayboard
supplies PostgreSQL stores through its composition root and keeps scheduling clarification policy in
its product layer.

Command submission uses an explicit Unit of Work to persist an idempotency claim, Thread, Run,
`run_created` event, and user message atomically. Idempotency records and validation remain
persistence-neutral; the active PostgreSQL implementation is supplied by Dayboard until the adapter
contract is ready to move into this package.

The package is internally divided by dependency direction:

```text
agent_platform.core         contracts and errors
agent_platform.ports        interfaces implemented by infrastructure
agent_platform.application  product-neutral use cases
```

Core cannot import Ports or Application. Ports depend only on Core. Application depends on Core and
Ports. The package intentionally has no concrete PostgreSQL or North adapter today: a technology
adapter belongs in an optional extra only after a second product proves the same contract.

Dependency direction:

```text
Dayboard ------> agent_platform
   |
   +-----------> North

future products -> agent_platform
future products -> their chosen runtime
```

North provides the Agent runtime, LangGraph checkpointing, and streaming. `agent_platform` provides
durable application lifecycle rules through a `RunExecutionDriver` port. A product-owned adapter
bridges the two, so neither lower-level package imports the other. This package must not import
`dayboard` or contain scheduling, calorie, exercise, or other product domain semantics. See
[ADR-008](../../docs/adr/008-introduce-agent-application-platform.md),
[ADR-009](../../docs/adr/009-keep-platform-and-north-independent.md), and the
[extraction guide](../../docs/agent-platform-extraction.md).
