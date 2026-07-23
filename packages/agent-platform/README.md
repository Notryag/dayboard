# Agent Application Platform

`agent_platform` is the reusable application layer between North and products such as Dayboard.

The package currently establishes an installable boundary only. Runtime capabilities will move in
tested vertical slices, beginning with Conversation + Run. Until a slice is complete, its Dayboard
implementation remains authoritative.

Dependency direction:

```text
North <- agent_platform <- Dayboard
                         <- future products
```

This package must not import `dayboard` or contain scheduling, calorie, exercise, or other product
domain semantics. See [ADR-008](../../docs/adr/008-introduce-agent-application-platform.md) and the
[extraction guide](../../docs/agent-platform-extraction.md).
