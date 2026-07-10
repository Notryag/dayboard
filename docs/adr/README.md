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

Initial ADRs to add when implementation starts:

- choose Next.js for the first UI
- use PostgreSQL from Phase 1
- keep `CalendarEntry` out of `north`
- use `tenant_id` with future isolation resolver
- choose the first worker/queue implementation

## Accepted Decisions

- [ADR-001: Adopt DeerFlow Run and Runtime Patterns](./001-adopt-deerflow-run-runtime-patterns.md)
