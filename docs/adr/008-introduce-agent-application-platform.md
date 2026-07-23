# ADR-008 Introduce An Agent Application Platform Layer

## Status

Accepted

## Context

Dayboard currently has two architectural layers:

```text
North runtime <- Dayboard product
```

This keeps scheduling concepts out of North, but Dayboard now also contains application capabilities
that are not specific to scheduling: authenticated identity context, conversations, Runs, persisted
message history, artifact recovery, clarification, media input, reminder delivery infrastructure,
and provider usage accounting.

Future products such as a nutrition or exercise recorder need many of those capabilities without
depending on Dayboard's calendar, task, prompt, tool, or presentation models. Copying them would
split fixes and operational behavior across products. Moving them into North would make the runtime
aware of application policy and persistence, reversing the dependency direction that keeps North
reusable.

## Decision

Introduce a third, independently installable layer:

```text
North <- Agent Application Platform <- Dayboard
                                   <- future products
```

The arrow is an import dependency: `Dayboard -> Agent Application Platform -> North`. A consumer
points to the dependency it imports. Runtime calls and data may flow in both directions through
declared interfaces, but that does not reverse the source-code dependency. A lower layer must never
import a higher layer.

### North owns runtime primitives

North owns product-neutral model invocation, agent loops, middleware execution, checkpoints,
canonical runtime events, Run execution mechanics, stream bridges, and runtime compaction timing.
It does not own users, tenants, HTTP APIs, product conversations, product reminders, or domain
artifacts.

### Agent Application Platform owns reusable application capabilities

The platform layer owns contracts and use cases that are valuable across multiple conversational
products:

- trusted tenant and user context;
- conversation threads, cursor-paginated messages, and durable history;
- product Run records, idempotent command submission, recovery, cancellation, and status mapping;
- typed message artifacts and refresh recovery;
- clarification and other resumable user interactions;
- media ingestion boundaries;
- notification delivery infrastructure;
- provider usage and budget records.

The platform does not decide what a calendar entry, task, meal, calorie, workout, or product card
means. Reusable infrastructure must accept explicit product adapters instead of importing product
modules.

The three layers describe logical ownership, not one flat module per layer. The platform is
internally separated into:

- `core`: identity, Conversation, Run, Interaction, and error contracts without framework imports;
- `application`: transaction-scoped use cases and lifecycle state machines;
- `ports`: storage, runtime execution, event publication, and product projection interfaces;
- `adapters`: optional PostgreSQL and North integrations that implement those ports.

Adapters depend inward on platform contracts. Platform Core and application use cases do not
depend on SQLAlchemy, FastAPI, a product package, or a concrete model provider. A North adapter may
depend on North without allowing North concepts to leak into the product-neutral contracts.

### Dayboard owns scheduling product semantics

Dayboard owns calendar entries, tasks, reminders as scheduling policy, scheduling repositories and
services, tool schemas, prompts, time classification, schedule receipts, schedule presentation
parts, and the Dayboard UI.

Northgate remains a sidecar for measurement and diagnostics. It is not part of the three-layer
application dependency chain and must not mutate application context.

## Consistency And Extension Boundaries

Platform use cases own their atomicity requirements. A Run transition and its durable lifecycle
event, or an idempotency claim and the Run/message created by that claim, must commit or roll back as
one unit. Store ports must therefore be composed through an explicit Unit of Work; correctness may
not rely on several repositories happening to share an unexpressed SQLAlchemy Session.

Product data crosses the platform boundary in versioned envelopes. The platform owns envelope
identity, schema version, lifecycle, persistence, and replay. The product owns and validates the
payload. This permits Dayboard schedule cards and a future nutrition product to use the same durable
pipeline without introducing a universal domain `Item` or allowing unversioned `dict[str, Any]` to
become a permanent protocol.

Resumable interactions use optimistic concurrency. The platform owns source Run correlation,
expiry, state version, and atomic claim/resolve behavior. Dayboard owns scheduling candidates,
choice labels, local-time projection, and the command produced from a selected choice.

## Package Boundary

The platform package lives at `packages/agent-platform` and imports as `agent_platform`. Dayboard
will consume it through public package APIs after each extraction slice is complete. Imports from
`agent_platform` to `dayboard` are prohibited and checked in CI.

North is maintained in its own repository. Its existing rule that it must not import Dayboard or
the platform remains enforced there. Dynamic imports may not be used to bypass either boundary.

The dependency guard is expanded incrementally to cover platform Core framework independence and
Dayboard's internal direction. Passing an import check is necessary but not sufficient: adapter
contract tests, transaction rollback tests, optimistic-concurrency tests, and tenant-isolation tests
must also exercise the assembled production path.

The package is introduced before runtime migration so ownership has a real destination and new
reusable code does not continue accumulating inside Dayboard.

## Extraction Strategy

Use tested vertical slices rather than moving folders wholesale:

1. establish the package, ownership map, and dependency guard;
2. extract Conversation + Run together with the minimum identity and artifact contracts they need;
3. switch Dayboard to the extracted public API and remove the original implementation;
4. make transaction ownership, idempotency, and persistence-neutral records explicit before moving
   more orchestration;
5. extract versioned presentation and resumable-interaction envelopes with atomic resolution;
6. split generic command submission and Run coordination from Dayboard Agent execution and result
   projection;
7. extract media, usage, and notification infrastructure only when their product adapters are
   explicit;
8. keep scheduling reminders, tools, prompts, domain models, and UI in Dayboard.

There is no compatibility layer for unreleased internal imports. Each completed slice has one
implementation and removes the previous path.

## Rejected Alternatives

### Put all reusable behavior in North

Rejected because authentication, product persistence, HTTP policy, and notification delivery are
application concerns. North would become coupled to one deployment model and eventually import
concepts from its consumers.

### Build a universal item model

Rejected because calendars, meals, workouts, and future products have different invariants. A
generic JSON item would move domain validation out of the database and into convention.

### Copy Dayboard for each new product

Rejected because Run recovery, conversation history, usage accounting, and security fixes would
diverge immediately.

### Perform a big-bang extraction

Rejected because the current modules mix reusable orchestration with scheduling policy. Moving the
files first would preserve the wrong coupling under a new package name.

## Consequences

The architecture gains a reusable middle layer without contaminating North or weakening product
domain models. Dependency violations fail in CI, and extraction can proceed one complete workflow
at a time.

The immediate cost is another package, explicit transaction boundaries, versioned extension
contracts, and adapter design. Until a slice is migrated, the current Dayboard implementation
remains authoritative; target ownership is never presented as an implemented platform feature.
