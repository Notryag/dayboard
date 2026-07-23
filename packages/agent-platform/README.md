# Agent Application Platform

`agent_platform` is the reusable application layer between North and products such as Dayboard.

The first extraction slice provides the trusted `TenantContext` plus product-neutral Conversation
and Run contracts. Dayboard imports these contracts directly; their former Dayboard definitions
have been removed. Persistence and lifecycle services still live in Dayboard until their ports can
be separated from scheduling-specific clarification and presentation behavior.

Dependency direction:

```text
North <- agent_platform <- Dayboard
                         <- future products
```

This package must not import `dayboard` or contain scheduling, calorie, exercise, or other product
domain semantics. See [ADR-008](../../docs/adr/008-introduce-agent-application-platform.md) and the
[extraction guide](../../docs/agent-platform-extraction.md).
