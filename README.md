# Dayboard

Dayboard is a scheduling and planning app that uses the `north` agent harness as its core runtime.

## Purpose

Dayboard is the product layer.

It is responsible for:

- voice or text input
- calendar and task data models
- calendar and planning workflows
- user-facing confirmation and clarification flows
- app-specific APIs and UI

It is not responsible for implementing the reusable agent harness itself.

That logic lives in the `north` package from the `deerflow-lite` repository.

## Relationship To North

`north` provides reusable agent capabilities such as:

- agent construction
- runtime execution
- tool orchestration
- skill loading
- thread and artifact handling
- streamed runtime events

Dayboard should consume those capabilities rather than re-implement them.

`north` owns runtime concepts such as `StreamEvent` and `RunEvent`. Dayboard owns product concepts such as `CalendarEntry` and `TaskItem`.

## Technology Direction

- Frontend: Next.js, React, TypeScript
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- Agent runtime: `north`
- Database: PostgreSQL
- Queue/cache/stream fanout: Redis or Valkey
- Worker runtime: async Python worker, with `arq` as the first candidate
- Object storage: S3-compatible storage for voice audio and attachments

## First Goal

The first usable Dayboard loop should be:

1. Accept text input, then later voice-to-text input.
2. Extract a structured scheduling intent.
3. Ask follow-up questions when required fields are missing.
4. Create a task or calendar entry.
5. Return a clear confirmation message.

## Initial Docs

- [docs/README.md](./docs/README.md)
- [docs/PROJECT_STATE.md](./docs/PROJECT_STATE.md)
- [docs/product-and-scope.md](./docs/product-and-scope.md)
- [docs/architecture.md](./docs/architecture.md)
- [docs/phase-1-plan.md](./docs/phase-1-plan.md)
- [docs/engineering-guidelines.md](./docs/engineering-guidelines.md)
- [docs/ui-design.md](./docs/ui-design.md)
- [docs/adr/README.md](./docs/adr/README.md)
