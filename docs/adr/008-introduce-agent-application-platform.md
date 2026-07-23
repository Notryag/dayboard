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

Arrows point from a dependency to its consumer. A higher layer may import a lower layer. A lower
layer must never import a higher layer.

### North owns runtime primitives

North owns product-neutral model invocation, agent loops, middleware execution, checkpoints,
canonical runtime events, Run execution mechanics, stream bridges, and runtime compaction timing.
It does not own users, tenants, HTTP APIs, product conversations, product reminders, or domain
artifacts.

### Agent Application Platform owns reusable application capabilities

The platform layer may depend on North and infrastructure libraries. It owns contracts and use
cases that are valuable across multiple conversational products:

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

### Dayboard owns scheduling product semantics

Dayboard owns calendar entries, tasks, reminders as scheduling policy, scheduling repositories and
services, tool schemas, prompts, time classification, schedule receipts, schedule presentation
parts, and the Dayboard UI.

Northgate remains a sidecar for measurement and diagnostics. It is not part of the three-layer
application dependency chain and must not mutate application context.

## Package Boundary

The platform package lives at `packages/agent-platform` and imports as `agent_platform`. Dayboard
will consume it through public package APIs after each extraction slice is complete. Imports from
`agent_platform` to `dayboard` are prohibited and checked in CI.

North is maintained in its own repository. Its existing rule that it must not import Dayboard or
the platform remains enforced there. Dynamic imports may not be used to bypass either boundary.

The package is introduced before runtime migration so ownership has a real destination and new
reusable code does not continue accumulating inside Dayboard.

## Extraction Strategy

Use tested vertical slices rather than moving folders wholesale:

1. establish the package, ownership map, and dependency guard;
2. extract Conversation + Run together with the minimum identity and artifact contracts they need;
3. switch Dayboard to the extracted public API and remove the original implementation;
4. extract clarification/media, usage, and notification infrastructure only when their product
   adapters are explicit;
5. keep scheduling reminders, tools, prompts, domain models, and UI in Dayboard.

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

The immediate cost is another package and explicit adapter design. Until a slice is migrated, the
current Dayboard implementation remains authoritative; the package skeleton is not presented as an
implemented platform feature.
