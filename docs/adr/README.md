# Architecture Decision Records

Use this directory for decisions that will be expensive to reverse or that affect multiple parts of Dayboard.

Suggested format:

```text
# ADR-000 Title

## Status

Proposed | Accepted | Superseded

## Context

What problem forced the decision?

## Decision

What are we choosing?

## Consequences

What gets easier, what gets harder, and what follow-up work does this imply?
```

Create another ADR when a new decision in one of these areas becomes expensive to reverse:

- UI framework or component-system replacement
- database or tenancy-isolation strategy
- Dayboard/North ownership boundary
- worker or queue replacement
- authentication or external notification provider boundary

## Accepted Decisions

- [ADR-001: Adopt DeerFlow Run and Runtime Patterns](./001-adopt-deerflow-run-runtime-patterns.md)
- [ADR-002: Adopt DeerFlow Runtime Observability Boundaries](./002-adopt-deerflow-runtime-observability.md)
- [ADR-003: Separate Conversation and Checkpoint Persistence](./003-separate-conversation-and-checkpoint-persistence.md)
- [ADR-004: Adopt Callback-First Token Accounting](./004-adopt-callback-first-token-accounting.md)
- [ADR-005: Authenticated Identity Boundary](./005-authenticated-identity-boundary.md)
- [ADR-006: Tenant Isolation and External Tool Boundaries](./006-tenant-isolation-and-external-tools.md)
- [ADR-007: Stream Canonical Agent Messages](./007-stream-canonical-agent-messages.md)
