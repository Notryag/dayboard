# Current Product Model

Dayboard is a self-service, voice-first scheduling product. A user speaks or types an instruction,
Dayboard creates or changes a calendar entry or task through tools, and the conversation renders the
authoritative result alongside an inspectable day view.

## Scheduling Classification

Classification follows the temporal anchor in the user's meaning:

| Meaning | Product object |
| --- | --- |
| Resolvable date, clock time, or daypart | Calendar entry |
| Date without a clock or daypart | `anytime` calendar entry |
| No resolvable temporal anchor | Undated task |
| Vague time such as “later” or “when free” | Undated task |

Examples:

- “明天早上 8 点吃药” creates a timed calendar entry at 08:00.
- “明天下午提交报告” creates a timed calendar entry using the afternoon default.
- “明天提交报告” creates an `anytime` calendar entry for tomorrow.
- “晚点整理资料” creates an undated task.

Daypart defaults are deterministic and apply only after an action is classified as a calendar
entry. The current defaults are defined in the Agent policy and protected by prompt tests.

## Calendar Entry

A calendar entry is one of two timing shapes:

```text
timed
  timing_kind = timed
  start_time and end_time are timezone-aware timestamps
  scheduled_date is null

anytime
  timing_kind = anytime
  scheduled_date is a product-local date
  start_time and end_time are null
```

Common fields include title, trusted IANA timezone, participants, reminder, status, tenant/owner
scope, audit timestamps, and Run correlation. Status is `scheduled`, `completed`, or `cancelled`.

Timed entries default to one hour when duration is omitted. Dayboard automatically checks clock
overlap during timed creation and rescheduling. Anytime entries have no clock overlap and no clock
reminder.

## Task Item

A task represents an action without a resolvable temporal anchor. It has a title and status
(`open`, `completed`, or `cancelled`). The storage model still supports `due_at`, but current Agent
classification sends any resolvable date or time to the calendar domain; the normal creation path
therefore creates undated tasks.

Tasks do not occupy a calendar interval. A task reminder requires a due timestamp and is anchored to
that timestamp.

## Reminder

Reminder intent uses an ISO 8601 offset and an anchor. Timed Agent-created calendar entries default
to an at-start `PT0M` reminder unless the user disables or overrides it. Anytime entries do not
invent clock reminders.

Application services synchronize schedule changes with durable reminder-delivery rows. The current
delivery channel is `in_app`. Delivery attempts, status, provider identifiers, and errors are stored
for inspection. Delivered rows carry durable per-account `read_at` state. The Web header exposes an
in-app reminder center with unread count, source-date navigation, read marking, delivery status,
and failed-delivery retry. Users may opt into browser Notifications while the Web app is active;
the same reminder ID is shown once per browser session. Retry returns the row to `pending`; the
worker remains the only delivery executor.

Delivery lifecycle is explicit:

| State | Meaning | User inbox |
| --- | --- | --- |
| `pending` | Waiting for its delivery time or an explicit retry | Hidden |
| `processing` | Claimed by one Worker | Hidden |
| `delivered` | In-app delivery completed | Visible |
| `failed` | Delivery attempted but failed and may be retried | Visible |
| `expired` | A calendar reminder was not delivered before the entry started | Hidden |
| `cancelled` | The source was completed, cancelled, deleted, or replaced | Hidden |

`read_at` is independent inbox state, not another delivery status. Future timed calendar entries and
entries still within the delivery grace can own a pending reminder. The Worker has a deterministic
two-minute claim grace after the calendar start so an at-start `PT0M` reminder survives the
15-second polling interval and brief scheduling jitter; exactly two minutes late is still
deliverable, while anything later is `expired` and is never redelivered. A future entry whose
configured reminder offset has just passed may be delivered immediately. Open task reminders remain
actionable after their due time and may still be delivered.
Completing, cancelling, rescheduling, or replacing a source changes every retryable active delivery
(`pending`, `processing`, or `failed`) to `cancelled`; already delivered rows remain as reminder
history. Completed calendar entries and tasks remain visible in the schedule view so users can
inspect or reopen them.

The delivery queue is not the user inbox. The Web reminder center receives only `delivered` and
`failed` items. Each inbox item projects the source's current title, occurrence time, and lifecycle
status from the authoritative calendar/task row. Rescheduled or renamed items therefore navigate
to and display the current source; cancelled or deleted sources remain honest, non-actionable
history. A missing source is reported as deleted rather than silently presenting stale payload data
as a live schedule item.

## Conversation And Clarification

Conversation threads and messages are durable and owner-scoped. Bounded context and persisted
compaction summaries prevent full history from being sent to every model call.
The mobile client resolves the owner's primary Thread from PostgreSQL before loading history.
Device-local storage never determines conversation ownership, so another device restores
the same durable history instead of silently creating a separate conversation.
The product exposes one primary conversation per owner. The first screen loads the newest 30
messages, and scrolling upward follows an owner-scoped `(created_at, id)` cursor to fetch older
pages without shifting the visible scroll position. Isolated evaluation Threads are active,
non-primary records (`is_primary = false`); they are not product conversations and do not appear in
this history. `active | archived` describes lifecycle only, and archived Threads cannot accept new
Runs.

When missing information would materially change the result, the Agent uses structured
clarification. Dayboard persists the question and trusted option mapping in `conversation_states`.
The browser receives stable option keys and display data, not database IDs or optimistic-lock
versions. The persisted Interaction has a schema identity, source Run, expiry, and monotonically
increasing state version. A selected option compare-and-consumes that exact version in the same
transaction that creates the idempotent follow-up Run, lifecycle event, and user message. Two
competing choices cannot both succeed, while retrying the same accepted request returns its existing
Run even though the Interaction has already been consumed.

The Agent does not ask for confirmation when the target and requested action are unambiguous.

## Identity And Ownership

Users can register with password authentication. Server-side sessions use secure `HttpOnly`
cookies. Membership and profile records resolve trusted tenant, owner, timezone, and locale context.

Every conversation, Run, schedule object, transcript, reminder, and provider usage record is scoped
by tenant and owner. Browser headers, user text, queued job payloads, and model arguments cannot
override that scope.

Scheduling currently resolves local time with the trusted account context, which defaults to
`Asia/Shanghai`. Explicit foreign-timezone conversion is not supported.

The product displays this zone as `北京时间`. Model-visible scheduling values use Beijing local
wall-clock time without an offset; PostgreSQL stores absolute instants as `timestamptz` under a UTC
session. See [Time And Concurrency Protocol](time-protocol.md).

## Product Surfaces

The mobile H5 application has two equal surfaces:

- conversation for voice/text capture, streaming progress, clarification, and result cards;
- schedule for a date rail, chronological agenda, undated tasks, editing, completion, cancellation,
  settings, appearance, and logout.

One full-width surface is selected from the transparent header and horizontal swipe. Dayboard does
not define a desktop layout or desktop fallback. Conversation schedule cards omit the completion
checkbox; mutations are available from the detail interaction.

## Current Scope Limits

Not implemented:

- recurring schedule engine;
- external calendar synchronization;
- multi-user collaboration and organization administration;
- billing;
- native mobile applications;
- foreign-timezone natural-language conversion;
- installed-PWA background notification delivery.

The canonical tool contract is documented in [../tool-design.md](../tool-design.md). Historical
product phases are retained only under [../archive](../archive/README.md).
