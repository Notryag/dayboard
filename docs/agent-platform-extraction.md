# Agent Application Platform Extraction

This is the active migration guide for [ADR-008](./adr/008-introduce-agent-application-platform.md).
It describes target ownership, not the currently deployed module layout. Canonical implemented
facts remain in `docs/current/`.

## Layer Contract

```text
Dayboard
  scheduling product and UI
    |
    | imports
    v
Agent Application Platform
  reusable application capabilities
    |
    | optional North adapter imports
    v
North
  runtime primitives only
```

The same platform may be consumed by future sibling products. Sibling products never import each
other. The arrows above show source-code imports, not runtime event or return-value flow.

The Platform remains one logical layer while separating its own responsibilities:

```text
agent_platform/
  core/          framework-free contracts and state rules
  application/   transaction-scoped use cases
  ports/         storage, runtime, publishing, and projection interfaces
  adapters/      optional PostgreSQL and North implementations
```

This internal structure does not introduce another product layer. It prevents persistence and North
integration details from becoming dependencies of the reusable Core.

## Current Ownership Map

| Current scope | Current owner | Target owner | Migration note |
| --- | --- | --- | --- |
| North agent loop, middleware, checkpoints, StreamBridge | North | North | Already correctly owned |
| Trusted `TenantContext` contract | Platform | Platform | Extracted; Dayboard retains only development-context construction |
| Conversation thread/message/state contracts | Platform | Platform | Extracted; former Dayboard domain module removed |
| Conversation service | Platform | Platform | Core service extracted; transaction and adapter reuse still need hardening |
| PostgreSQL Conversation repositories | Dayboard adapter | Platform adapter | Move only after Unit of Work and Store contracts are proven |
| Run and Run-event contracts | Platform | Platform | Extracted; former Dayboard domain module removed |
| Run lifecycle service | Platform | Platform | Core lifecycle extracted; Unit of Work is not yet explicit |
| PostgreSQL Run repositories | Dayboard adapter | Platform adapter | Move only after lifecycle concurrency contracts are proven |
| Command idempotency | Dayboard | Platform | Replace direct ORM Row access with a platform record, Store, and service |
| Command submission and dispatch | Mixed | Split | Platform owns generic lifecycle; Dayboard supplies agent/product adapters |
| Persisted message artifacts | Mixed | Split | Platform owns a versioned envelope and lifecycle; Dayboard owns schedule payloads |
| Clarification interaction state | Dayboard | Split | Platform owns concurrency/lifecycle; Dayboard owns scheduling choices and responses |
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

## Architecture Review Findings

The first extraction established the correct package direction, but it is not the final application
boundary. The following gaps must be closed before moving more capabilities:

1. `AgentRunService` updates a Run and appends its event through separate Store calls while Dayboard
   callers currently control `commit()`. The shared Session makes today's PostgreSQL path atomic,
   but the platform contract does not express or guarantee that invariant.
2. `ConversationService` is intentionally thin, while primary-thread uniqueness, pagination, and
   idempotent message persistence remain implemented in Dayboard PostgreSQL repositories. This is a
   valid intermediate state, not yet a reusable persistence implementation.
3. `message_metadata`, `state_data`, and `event_metadata` are currently unversioned mappings. They
   are storage shapes, not an acceptable permanent cross-product contract.
4. Command submission reads `IdempotencyKeyRow` directly, leaking an ORM model into the application
   use case.
5. Clarification validates a previously read state version but does not atomically consume that
   version. Concurrent responses from two clients can race.
6. `ConversationThread.status` is a free string and currently conflates lifecycle state with primary
   versus isolated conversation role.
7. The dependency check prevents only `agent_platform -> dayboard`; it does not yet enforce
   framework-free Platform Core or Dayboard's internal dependency direction.

These findings do not require replacing the three-layer model. They define the hardening work needed
to make that model robust rather than merely moving files between packages.

## Required Consistency Boundaries

The platform Unit of Work must make each group atomic:

```text
command submission
  idempotency claim + Thread resolution + Run + user message + run_created event

Run transition
  compare-and-transition Run + corresponding durable event

interaction resolution
  compare-and-consume interaction version + continuation Run/message creation
```

Agent execution remains outside a database transaction. Each durable checkpoint above uses a short
transaction; no transaction is held open while waiting for a model, tool provider, Redis, or SSE
consumer.

Event ordering must also be safe under concurrent writers. PostgreSQL event sequence allocation
cannot rely permanently on an unlocked `max(seq) + 1` calculation.

## Versioned Extension Contracts

The platform may persist product-specific data, but it does not interpret it:

```text
PresentationEnvelope
  kind
  schema_version
  payload             validated by the product adapter

PendingInteraction
  interaction_type
  schema_version
  source_run_id
  version
  expires_at
  payload             validated by the product adapter
```

Dayboard continues to own `ScheduleResultPart`, scheduling receipts, candidate shapes, and local-time
projection. North continues to own transient `ToolMessage.content` and `ToolMessage.artifact`
transport. The Platform owns only durable envelope persistence, replay, and interaction lifecycle.
The same model context must never receive both UTC entity timestamps and local-time receipts.

## Definition Of Done For A Slice

A capability is considered extracted only when:

- Dayboard imports its public API from `agent_platform`;
- the old Dayboard implementation is deleted in the same slice;
- migrations and data remain authoritative in PostgreSQL;
- multi-store writes execute through an explicit Unit of Work and rollback together;
- tenant isolation, idempotency, recovery, and concurrency tests pass through the platform API;
- persisted extension payloads carry a schema identity/version and are validated by their owner;
- ORM rows, FastAPI types, and concrete runtime types do not cross Core/application ports;
- the platform package has no `dayboard` import and no scheduling vocabulary in its public models;
- production has one execution path, with no compatibility adapter for the removed internal path;
- `docs/current/` is updated only after the new path is actually active.

## Guardrails

- Do not begin with a shared `Item`, arbitrary JSON domain storage, or a universal tool schema.
- Do not move modules based only on similar filenames; split mixed ownership at explicit ports.
- Do not add platform APIs for hypothetical consumers. Extract a capability already proven by
  Dayboard and shape it around stable invariants.
- Do not treat a Store Protocol plus a forwarding service as a completed reusable capability when
  transaction and persistence semantics still live only in Dayboard.
- Do not let `dict[str, Any]` become an unversioned public protocol. Opaque product payloads require
  a platform-owned envelope and product-owned validation.
- Do not hold a database transaction across model execution, external providers, Redis publication,
  or client streaming.
- Do not let package extraction change user-visible behavior in the same commit.
- Keep Northgate observational. It may report Run/token data but cannot choose prompts, compact
  context, or alter business writes.

## Milestones

1. Package skeleton, ADR, ownership map, and CI dependency check. Complete.
2. Trusted identity plus Conversation/Run contracts and focused contract tests. Complete.
3. Run repository ports and platform lifecycle service; remove original Run service. Complete.
4. Conversation repository ports and platform service; remove original service path. Complete.
5. Correct dependency documentation and record the architecture hardening gaps. Complete.
6. Add Platform Core and Dayboard Domain dependency checks. Complete.
7. Add Unit of Work and platform idempotency contracts; remove ORM records from command use cases.
8. Add versioned presentation envelopes and atomically resolved Interaction contracts.
9. Split generic command submission/Run coordination from Dayboard Agent and result projection.
10. Add reusable PostgreSQL/North adapters only where their contracts have been proven by the active
   Dayboard path.
11. Consider usage accounting and notification delivery only after the lifecycle adapters are
    demonstrated.
