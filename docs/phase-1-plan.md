# Phase 1 Plan

## Goal

Ship the smallest loop that proves Dayboard can use `north` as its core agent capability.

## Phase 1 Workflow

```text
user text input
  -> scheduling intent extraction
  -> clarification if needed
  -> create calendar entry or task
  -> confirmation response
```

## Required Components

1. App skeleton with `apps/api` and `apps/web`
2. `north` dependency wiring
3. `CalendarEntry` and `TaskItem` schemas
4. PostgreSQL storage
5. Alembic migrations
6. scheduling tools
7. minimal prompt and intent loop
8. Next.js web entry point
9. tests for create-calendar-entry and clarification flows

PostgreSQL is the Phase 1 storage choice. Dayboard is intended to grow into a commercial product, so the first implementation should use a production-capable database instead of SQLite or JSON files.

Redis or Valkey should be introduced when background agent jobs and run streaming need queue/fanout support. It should not be the source of truth.

Engineering work should follow [engineering-guidelines.md](./engineering-guidelines.md).

## Suggested First Milestones

### M1

- create project package layout
- wire local dependency on `north`
- define `CalendarEntry` and `TaskItem` models
- define `TenantContext`
- add PostgreSQL session wiring
- add Alembic baseline migration

### M2

- add `create_calendar_entry` and `create_task_item`
- add `list_calendar_entries` and `list_task_items`
- return deterministic results through a simple interface
- call tools from structured input before connecting the LLM
- add repository tests against PostgreSQL

Any command API added in M2 is temporary. It may return a hard-coded clarification only to keep the frontend/API contract moving before the agent loop exists. That fallback must be removed or replaced in M3 when `north` owns command interpretation and clarification.

### M3

- connect agent loop to scheduling tools
- support missing-field clarification
- verify text-based schedule creation end to end

### M4

- add Next.js command input and list views
- generate or hand-write the first TypeScript API client
- display run status and clarification questions

### M5

- add background run worker boundary
- add run event persistence
- add SSE endpoint for run updates

### M6

- add voice input boundary design
- decide ASR provider contract

## Success Criteria

Phase 1 is successful when a user can create a task or calendar entry from natural language in the Next.js app and receive a correct confirmation, with clarification when required fields are missing.

## Testing Rhythm

Use slice-based testing. Do not wait until the end to add tests, and do not require strict test-first development for every small piece.

Default rhythm:

```text
implement a small vertical slice
  -> add deterministic tests for domain, repository, or tool behavior
  -> add API tests once the endpoint exists
  -> add agent-flow tests after tool behavior is stable
```

For Phase 1, deterministic tests should come before broad LLM flow tests. The create-calendar-entry and create-task-item paths should be testable without calling a model.

## Non-Goals

- no dedicated database per tenant
- no billing
- no production organization admin UI
- no external calendar sync
- no real push notifications
- no full mobile app

The schema and service signatures should still carry tenant context so these can be added later without rewriting the product tools.
