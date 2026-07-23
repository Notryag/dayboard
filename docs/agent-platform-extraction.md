# Agent Application Platform Extraction

This is the active migration guide for [ADR-008](./adr/008-introduce-agent-application-platform.md).
It describes target ownership, not the currently deployed module layout. Canonical implemented
facts remain in `docs/current/`.

## Layer Contract

```text
North
  runtime primitives only
    ^
    |
Agent Application Platform
  reusable application capabilities
    ^
    |
Dayboard
  scheduling product and UI
```

The same platform may be consumed by future sibling products. Sibling products never import each
other.

## Current Ownership Map

| Current scope | Current owner | Target owner | Migration note |
| --- | --- | --- | --- |
| North agent loop, middleware, checkpoints, StreamBridge | North | North | Already correctly owned |
| `dayboard.context.TenantContext` | Dayboard | Platform | Extract only trusted identity contract; product defaults stay in Dayboard |
| Conversation thread/message/state models and repositories | Dayboard | Platform | First extraction slice |
| Run models, repositories, lifecycle and idempotency | Dayboard | Platform | Move with conversations so recovery remains atomic |
| Command submission and dispatch | Mixed | Split | Platform owns generic lifecycle; Dayboard supplies agent/product adapters |
| Persisted typed message artifacts | Mixed | Platform contract | Dayboard continues defining schedule artifact payloads |
| Clarification interaction state | Dayboard | Platform | Extract after Conversation + Run |
| Voice/media ingestion lifecycle | Dayboard | Platform boundary | Provider and product interpretation remain adapters |
| Provider usage and budget accounting | Dayboard | Platform | Extract after lifecycle ownership stabilizes |
| Reminder delivery/outbox machinery | Mixed | Split | Platform may own delivery; Dayboard owns due-time and schedule policy |
| Auth credentials and account recovery | Dayboard | Platform candidate | Extract only with a concrete second consumer or stable identity API |
| Calendar/task domain, repositories and services | Dayboard | Dayboard | Never move to platform |
| Scheduling prompt, tools, time rules and receipts | Dayboard | Dayboard | Never move to platform |
| Schedule cards and Dayboard web UI | Dayboard | Dayboard | Never move to platform |
| Token diagnostics and cross-service budgets | Northgate | Northgate | Sidecar; no context mutation |

## First Vertical Slice: Conversation + Run

Conversation and Run move together because they share recovery and consistency boundaries:

```text
submit command
  -> append user message
  -> create Run idempotently
  -> execute product agent through North
  -> persist assistant message and artifacts
  -> finalize Run
  -> recover the same state after refresh or reconnect
```

The platform API must use injected ports for:

- transaction/session scope;
- product agent construction and execution;
- artifact validation and serialization;
- live event projection;
- command dispatch.

Dayboard keeps the scheduling implementations of those ports. The platform must not import a
Dayboard Pydantic model, SQLAlchemy row, tool name, prompt, or presentation type.

## Definition Of Done For A Slice

A capability is considered extracted only when:

- Dayboard imports its public API from `agent_platform`;
- the old Dayboard implementation is deleted in the same slice;
- migrations and data remain authoritative in PostgreSQL;
- tenant isolation, idempotency, recovery, and concurrency tests pass through the platform API;
- the platform package has no `dayboard` import and no scheduling vocabulary in its public models;
- production has one execution path, with no compatibility adapter for the removed internal path;
- `docs/current/` is updated only after the new path is actually active.

## Guardrails

- Do not begin with a shared `Item`, arbitrary JSON domain storage, or a universal tool schema.
- Do not move modules based only on similar filenames; split mixed ownership at explicit ports.
- Do not add platform APIs for hypothetical consumers. Extract a capability already proven by
  Dayboard and shape it around stable invariants.
- Do not let package extraction change user-visible behavior in the same commit.
- Keep Northgate observational. It may report Run/token data but cannot choose prompts, compact
  context, or alter business writes.

## Milestones

1. Package skeleton, ADR, ownership map, and CI dependency check.
2. Conversation/Run contracts and repository ports with focused contract tests.
3. Dayboard migration to the platform implementation and removal of original modules.
4. Clarification and artifact interaction contracts.
5. Usage accounting and notification delivery, only after adapters are demonstrated.
