# Agent Application Platform

`agent_platform` is the reusable application layer between North and products such as Dayboard.

The first extraction slice provides the trusted `TenantContext`, product-neutral Conversation and
Run contracts, and the storage-independent Run lifecycle service. Dayboard imports these directly;
their former Dayboard definitions and Run service have been removed. Dayboard supplies PostgreSQL
Run stores through its composition root. Conversation persistence and service orchestration remain
in Dayboard until scheduling-specific clarification behavior is separated behind an adapter.

Dependency direction:

```text
North <- agent_platform <- Dayboard
                         <- future products
```

This package must not import `dayboard` or contain scheduling, calorie, exercise, or other product
domain semantics. See [ADR-008](../../docs/adr/008-introduce-agent-application-platform.md) and the
[extraction guide](../../docs/agent-platform-extraction.md).
