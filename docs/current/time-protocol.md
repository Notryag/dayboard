# Time And Concurrency Protocol

Status: canonical current contract  
Last reviewed: 2026-07-23

## Invariants

Dayboard currently supports one trusted scheduling timezone. Its product name is `北京时间` and
its machine identifier is the IANA zone `Asia/Shanghai`.

| Boundary | Representation |
| --- | --- |
| Product display | Beijing Time |
| Model-visible tool input and receipt | Beijing local wall-clock value, no offset |
| Application/domain layer | timezone-aware Python `datetime` |
| PostgreSQL | `timestamp with time zone`, operated with a UTC database session |

`Asia/Shanghai` remains the internal IANA identifier. It must not be globally replaced with a
display label or a non-standard zone name. PostgreSQL stores absolute instants; the separate
`timezone` column preserves the trusted business zone used for display and local-date semantics.

An anytime calendar entry stores `scheduled_date` as a PostgreSQL `date`. It has no invented clock
instant and therefore no UTC conversion.

## Model-Visible Contract

The model reads and writes only Beijing local wall-clock values:

```json
{
  "id": "calendar-entry-id",
  "title": "钓鱼",
  "local_start": "2026-07-24T16:00",
  "local_end": "2026-07-24T17:00",
  "row_version": 3
}
```

The canonical precision is minutes and format is `YYYY-MM-DDTHH:mm`. Model-visible local fields
never contain `Z`, `+00:00`, `+08:00`, an IANA timezone, or a UTC timestamp. The model must not add
or subtract eight hours. Trusted runtime code attaches `Asia/Shanghai` at the tool boundary and
converts the resulting instant for storage.

Duration requests use duration rather than model-computed end times:

```json
{
  "calendar_entry_id": "calendar-entry-id",
  "new_duration_minutes": 30,
  "expected_row_version": 3
}
```

Explicit clock changes use `new_local_start` or `new_local_end` in the same format. Calendar search,
creation, mutation and conflict receipts, task due receipts, clarification-resume messages, and the
system reference clock must all follow this local-only rule.

The same model context must never contain both an absolute field and its local equivalent, for
example `start_time=08:00+00:00` together with `local_start=16:00`.

## ToolMessage Boundary

```text
ToolMessage.content  -> compact local-time receipt for the model
ToolMessage.artifact -> complete UTC/offset-aware entity for UI, SSE, and history restoration
```

Artifacts may include `start_time`, `end_time`, `due_at`, `timezone`, and audit timestamps. Artifact
data must never be serialized into a provider request. Provider-boundary tests must inspect the
actual messages sent to the model and reject absolute scheduling timestamps in ToolMessage content.

Structured clarification stores the complete presentation candidate for the UI. When a selected
candidate resumes Agent execution, Dayboard creates a model candidate containing only local fields
and `row_version`; it must not copy artifact timestamps into the generated user message.

## Database Conversion

The trusted conversion is program-owned:

```python
local_value = datetime.strptime(value, "%Y-%m-%dT%H:%M")
aware_value = local_value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
```

SQLAlchemy sends the aware value to PostgreSQL `timestamptz`. PostgreSQL normalizes the instant;
the production database session timezone is UTC. Reads return aware instants, which are converted
back to `Asia/Shanghai` only when building model receipts or product display values.

Browser REST APIs may carry offset-aware instants because they belong to the typed UI/artifact
boundary, not the model boundary. Browser rendering must use the trusted account timezone rather
than the device timezone.

## Optimistic Concurrency

Schedule entities use an integer database version instead of an audit timestamp:

```sql
row_version BIGINT NOT NULL DEFAULT 1
```

Every effective calendar or task mutation atomically applies:

```sql
UPDATE ...
SET row_version = row_version + 1,
    updated_at = now(),
    ...
WHERE id = :id
  AND row_version = :expected_row_version
RETURNING *;
```

Zero updated rows means the selected entity changed concurrently. `updated_at` remains available
for audit and ordering but is not a concurrency token. Model tools use `expected_row_version`, and
sequence creation uses `expected_anchor_row_version`. The Anchor row remains locked while its
version, active state, and authoritative `end_time` are checked.

All mutation paths increment the version: Agent reschedule/cancel/update, Web edit/cancel, calendar
complete/reopen, and task complete/reopen/cancel.

## Context Migration

Existing Agent checkpoints can contain legacy ToolMessages with UTC scheduling fields. The rollout
uses the new `dayboard-time-v2` checkpoint namespace, invalidating only the old runtime context while
preserving durable conversation messages and schedule entities. Provider-boundary sanitization also
removes artifacts and rewrites absolute fields defensively before every main-model request. New
summary input contains only the compact local-time receipt because the legacy namespace is never
loaded.

There is no model-schema compatibility branch for `expected_updated_at`, absolute receipt fields,
or model-provided timezone values. This project is pre-release; the new protocol replaces them.

## Required Tests

Tests must prove:

1. Local input and receipt fields use the same `YYYY-MM-DDTHH:mm` format.
2. Tool code, not the model, attaches `Asia/Shanghai` and PostgreSQL stores the correct instant.
3. Model receipts contain no `start_time`, `end_time`, `due_at`, timezone, `Z`, or numeric offset.
4. UI artifacts retain complete absolute timestamps and render identically after refresh.
5. Provider-bound messages never include artifact scheduling timestamps.
6. Duration updates modify only the selected entry unless another mutation is explicitly requested.
7. Adjacent entries are independent; shortening the first creates a gap and does not move the next.
8. Every mutation increments `row_version`, and stale versions fail atomically.
9. Anchor creation rejects a stale `expected_anchor_row_version`.
10. Clarification resume sends local fields and version only.
