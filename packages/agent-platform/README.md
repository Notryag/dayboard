# Agent Application Platform

`agent_platform` is the reusable application layer between North and products such as Dayboard.

The first extraction slice provides the trusted `TenantContext`, product-neutral Conversation and
Run contracts, and storage-independent Conversation and Run services. Dayboard imports these
directly; its former duplicate domain and service modules have been removed. Dayboard supplies
PostgreSQL stores through its composition root and keeps scheduling clarification policy in its
product layer.

Dependency direction:

```text
North <- agent_platform <- Dayboard
                         <- future products
```

This package must not import `dayboard` or contain scheduling, calorie, exercise, or other product
domain semantics. See [ADR-008](../../docs/adr/008-introduce-agent-application-platform.md) and the
[extraction guide](../../docs/agent-platform-extraction.md).
