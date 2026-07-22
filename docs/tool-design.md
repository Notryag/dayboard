# Agent Tool Design

Status: active contract  
Last reviewed: 2026-07-20

## Ownership Boundary

Dayboard owns scheduling semantics, persistence, authorization, and model-visible business tools.
North owns the generic Agent loop and middleware execution. The model proposes business fields;
the runtime injects trusted context and the server validates every operation.

The model never receives or supplies `tenant_id`, `user_id`, `run_id`, `operation_key`,
`*_by_run_id`, permissions, or the trusted default timezone. Local datetime fields have no offset
and are resolved with `TenantContext.timezone`. A future explicit foreign timezone may be an
optional model field, but it must never replace the trusted default implicitly.

`expected_updated_at` remains model-visible on mutations of existing objects. It is required for
optimistic locking and protects a selection from concurrent changes.

## Model-Visible Surface

Dayboard exposes seven scheduling tools:

| Domain | Tool | Responsibility |
| --- | --- | --- |
| Calendar | `create_calendar_entry` | Create one scheduled activity and return internal conflict results. |
| Calendar | `search_calendar_entries` | List or search calendar entries and answer overlap/availability queries. |
| Calendar | `reschedule_calendar_entry` | Move one selected entry and return internal conflict results. |
| Calendar | `cancel_calendar_entry` | Cancel one selected entry without hard deletion. |
| Task | `create_task_item` | Create one open task with no resolvable date or time. |
| Task | `search_task_items` | List or search tasks by optional title and status. |
| Task | `update_task_item` | Rename, complete, or cancel one selected task. |

`ask_clarification` is a runtime interaction tool, not a scheduling business tool. It remains
model-visible in every active tool set so ambiguous selections and missing required data use the
resumable interaction protocol. The total initial model-visible surface is therefore eight tools.

There are no separate list tools. An empty search query performs a bounded list operation. Calendar
search accepts an optional local interval; the server applies a documented default window when it
is omitted. Its interval predicate uses overlap semantics so an entry that starts before the query
but ends inside it is still returned. Results must have a server-side maximum and deterministic
ordering.

There is no model-visible conflict-check tool. Calendar creation and rescheduling check conflicts
inside the application service. Availability questions use `search_calendar_entries` with the
requested interval.

Search tools do not accept a `purpose`. Search identifies objects; the subsequent mutation tool is
the authoritative action. Progress text remains neutral, and interaction state is derived from
actual mutation/clarification flow rather than a model-provided search label.

New task status is not model-selectable. `create_task_item` always creates `open`; status changes use
`update_task_item`.

Classification is intentionally mechanical: any resolvable date, clock, or daypart creates a
calendar entry, even when the wording describes completion or a deadline. Calendar entries have
two explicit timing modes:

- `timed` stores a local clock time resolved to an instant. A daypart without a clock uses its
  deterministic default only after the action has been classified as a calendar entry.
- `anytime` stores only a local calendar date. Date-only expressions such as `明天提交报告` use
  this mode; the system must not invent `00:00`, `09:00`, or another hidden clock time.

An anytime entry has no start/end instant or reminder and does not participate in clock-overlap
conflict checks. It is included in calendar searches by its local date and rendered as `随时`.
Tasks have no model-visible date or time fields and are reserved for actions with no resolvable
temporal anchor, including vague expressions such as `晚点`, `有空`, and `抽空`.

## Input And Result Shape

Schemas contain only fields required to identify or perform the operation. Field descriptions own
format constraints; the system prompt owns cross-tool scheduling policy. Avoid repeating the same
policy in both places.

Model-visible write results contain:

- a stable result `type`;
- the authoritative calendar entry or task object;
- conflicts where calendar creation or rescheduling can produce them;
- an optional concise `summary` only when it adds information not obvious from the entity.

The model-visible result is a compact receipt in `ToolMessage.content`. The complete safe entity
snapshot is carried separately in `ToolMessage.artifact`, projected to typed SSE, and persisted in
conversation metadata. PostgreSQL remains authoritative for product state and visible history;
checkpoint artifacts are transport copies. See
[Context And Token Optimization](context-token-optimization.md).

Do not return a second top-level object ID when the authoritative entity already contains `id`.
Do not return `requires_follow_up=false`; clarification is represented by the interaction tool, not
a dormant result flag. Internal domain models may retain audit and idempotency fields, while the
Agent projection exposes only fields required for rendering and subsequent optimistic mutations.

Sequence-dependent creation uses `anchor_entry_id` plus `expected_anchor_updated_at` on
`create_calendar_entry`. These fields are mutually exclusive with direct date/start/end inputs.
After a search selects one timed entry, the service locks that tenant-owned row, verifies its
version and active state, derives the new start from its authoritative `end_time`, checks conflicts,
and creates the new entry in the same transaction. The model must not copy `end_time` into a direct
`local_start`; doing so would reintroduce a search/write race.

## Dynamic Binding

Dynamic binding is deterministic middleware over canonical tool messages. It does not add a model
selector call and does not classify user text with keywords.

| State | Bound tools |
| --- | --- |
| First semantic turn or new user turn | Seven scheduling tools plus `ask_clarification` |
| Successful calendar search result | Four calendar tools plus `ask_clarification` |
| Successful task search result | Three task tools plus `ask_clarification` |
| Successful terminal write result(s) | No scheduling tools; generate the grounded confirmation |
| Same tool-call batch spans calendar and task domains | Full tool surface until the batch resolves |
| Error, malformed result, or unavailable required tool | Restore the full surface for one recovery attempt |

Domain narrowing applies after search, where the next operation is known to stay in that domain. A
calendar or task write does not narrow to more write tools; a successful write enters confirmation.
This avoids hiding a task merely because a mixed command happened to execute a calendar write
first. A recovery marker must prevent unbounded restore/retry loops.

## Acceptance Contract

Tests must prove:

1. Exactly seven scheduling tools are assembled and trusted fields never enter their schemas.
2. `ask_clarification` remains available in full and domain-specific tool sets.
3. Empty searches are bounded and calendar interval searches detect overlaps.
4. Create and reschedule return conflicts without a separate conflict tool.
5. Task creation cannot select a non-open status.
6. Mutation results require and enforce `expected_updated_at`.
7. Successful searches narrow by domain, mixed batches retain the full surface, terminal writes
   remove tools, and failures restore the full surface once.
8. Stream projection and conversation cards render authoritative entities without duplicate IDs or
   `requires_follow_up` fields.
9. Date-only actions create searchable `anytime` entries with no start/end instant, reminder, or
   clock conflict; daypart actions remain timed.
10. Compact receipts stay within their token budgets while complete artifacts render identically
    live and after conversation refresh.
