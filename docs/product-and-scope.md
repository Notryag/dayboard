# Product And Scope

## Product Definition

Dayboard is a planning and scheduling product.

It is intended to be a publicly releasable, self-service product. Users can register directly;
private-beta invitations are not part of the default product model. Public access does not weaken
the ownership boundary: every user receives an isolated account and tenant context, and expensive
operations remain protected by rate limits and provider budgets.

Its first target use case is:

> create schedules, reminders, and lightweight plans from natural language, then evolve toward voice-first capture.

## Core User Outcome

A user should be able to say or type something like:

> Next Wednesday at 3pm, schedule a product review with Alice and remind me one day before.

The system should:

1. understand the request
2. identify missing information
3. ask a follow-up question if needed
4. create the calendar entry
5. confirm the created result

## In Scope For Phase 1

- text-first schedule creation
- structured intent extraction
- follow-up clarification
- create calendar entry
- create task
- simple list view or API result
- Next.js web app for the first user interface
- production-shaped backend and database foundation

## Minimum Data Contract

Phase 1 only needs enough structure to create, clarify, list, and confirm schedule data. The schema should stay small until external calendar sync or a richer planning engine requires more fields.

### CalendarEntry

A calendar entry represents something scheduled on a calendar. It is a Dayboard business object, not a `north` runtime event.

Required fields:

- `title`: short user-facing name
- `start_time`: timezone-aware start datetime
- `timezone`: IANA timezone, such as `Asia/Shanghai`

Optional fields:

- `end_time`: timezone-aware end datetime
- `participants`: people mentioned by the user
- `reminder`: stored reminder intent, such as `1 day before`
- `notes`: extra natural-language context

Defaults and clarification:

- Missing `title` should trigger clarification unless it can be safely inferred from the input.
- Missing `start_time` should trigger clarification.
- Missing `timezone` should default to the user's configured timezone.
- Missing `end_time` is allowed in Phase 1. The app may either store it as empty or apply a product default later.
- `reminder` was stored as intent only in Phase 1. Phase 2 resolves it into a durable delivery
  outbox; `in_app` delivery is implemented, while external push/SMS/WeChat delivery remains pending.

### Task

A task represents something to do. It may have a due time, but it does not occupy a calendar time range.

Required fields:

- `title`: short user-facing name
- `status`: `open`, `completed`, or `cancelled`

Optional fields:

- `due_at`: timezone-aware due datetime
- `timezone`: IANA timezone when `due_at` or `reminder` is present
- `reminder`: stored reminder intent
- `notes`: extra natural-language context

Defaults and clarification:

- Missing `title` should trigger clarification unless it can be safely inferred from the input.
- Missing `status` defaults to `open`.
- Missing `timezone` should default to the user's configured timezone when time data exists.
- A task without `due_at` is allowed.
- A task reminder requires `due_at` and is anchored to it.

## Out Of Scope For Phase 1

- multi-user collaboration
- external calendar sync
- push notifications
- recurring event engine
- full voice pipeline
- mobile app
- dedicated database per tenant
- billing and organization administration

## Dependency Direction

Dayboard depends on `north`.

`north` must not depend on Dayboard.

## Naming Rules

- Use `CalendarEntry` for a scheduled item in a user's calendar.
- Use `TaskItem` for a to-do item.
- Do not use plain `Event` for Dayboard business data, because `north` already has runtime events such as `StreamEvent` and `RunEvent`.
