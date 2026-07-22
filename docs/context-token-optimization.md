# Context And Token Optimization

Status: accepted implementation plan
Last reviewed: 2026-07-22

## Goal

Reduce model-visible scheduling history without weakening UI recovery, optimistic
locking, cross-turn scheduling semantics, or runtime observability. The motivating
production Runs compacted twice in one ordinary tool loop, while tool protocol
messages represented most of the retained conversation-history tokens.

## Ownership

```text
Dayboard   scheduling semantics, compact receipts, presentation artifacts, UI history
North      generic message lifecycle, stream transport, atomic retention, compaction timing
Northgate  provider token measurement, cache diagnostics, and budgets
```

North must not understand Dayboard entity fields. Northgate must not mutate Agent
context or infer compaction calls from provider traffic.

## Immediate Production Guardrail

Dayboard first stopped the production incident with the following temporary host configuration:

```env
DAYBOARD_SUMMARIZATION_TRIGGER_TOKENS=6000
DAYBOARD_SUMMARIZATION_TRIGGER_MESSAGES=60
DAYBOARD_SUMMARIZATION_KEEP_MESSAGES=12
```

The message-count keep value remained only until North supported a token-targeted
retention window. This guardrail has now been superseded by the Run-aware settings below; it stays
here as implementation history rather than an active configuration contract.

```env
DAYBOARD_SUMMARIZATION_NORMAL_TRIGGER_TOKENS=6000
DAYBOARD_SUMMARIZATION_EMERGENCY_TRIGGER_TOKENS=12000
DAYBOARD_SUMMARIZATION_MESSAGE_CEILING=60
DAYBOARD_SUMMARIZATION_TARGET_TOKENS=2000
DAYBOARD_SUMMARIZATION_MIN_GROWTH_TOKENS=3000
DAYBOARD_SUMMARIZATION_MAX_EMERGENCY_COMPACTIONS=2
```

Summary and model lifecycle events remain durable audit and
usage records, but Dayboard does not publish them to the user-facing SSE stream.
The product shows lifecycle and tool-level states such as processing, searching,
saving, and failure.

## Model Result And Presentation Artifact

Scheduling tools use LangChain's `content_and_artifact` response contract:

```text
ToolMessage.content   compact JSON ModelResult visible to the model
ToolMessage.artifact  full validated PresentationPart for the product projection
```

The compact result contains only fields needed for later reasoning:

- stable result type;
- entity ID and concise title;
- timing kind and scheduled date/start/end values;
- status and `updated_at` for optimistic locking;
- reminder or conflict summaries only when relevant.

It omits `created_at`, trusted fixed timezone, empty collections and reminders,
Run audit IDs, duplicate IDs, and unrelated conflict fields.

The artifact carries the complete safe `ScheduleDisplayItem` snapshot. After the
product transaction commits, Dayboard validates the artifact, publishes the
typed schedule result, and persists it in assistant conversation metadata.
PostgreSQL conversation metadata is authoritative for refresh recovery. A
LangGraph checkpoint artifact is a transport copy and may be removed during
later compaction after durable projection; it is not the product history store.

Required path:

```text
ToolMessage artifact
  -> LangGraph state
  -> North canonical message stream
  -> Redis StreamBridge
  -> Dayboard safe projector
  -> browser SSE reducer
  -> assistant conversation metadata
  -> refresh recovery
```

North transports JSON-compatible artifacts without interpreting them. Dayboard
rejects malformed or unsafe artifacts at its projection boundary.

## Run-Aware Compaction

North replaces the single threshold with two policies:

```text
Run start: history > 6000 tokens -> one normal compaction
Run execution: complete model-visible context > 12000 tokens -> emergency compaction
Target retained history: approximately 2000 tokens
Minimum growth before another compaction: 3000 tokens
Emergency compactions per Run: bounded to 2
```

Run-aware counters live in invocation state/runtime context, not mutable
middleware instance fields. A normal compaction occurs at most once per Run.
Retention is token-targeted and never separates an AI message's tool-call batch
from its corresponding ToolMessages. ToolMessage content is already a compact
host-defined receipt; North does not transform Dayboard business fields. Old
presentation artifacts may be dropped only after the host has durably projected
them.

`history_tokens` means serialized message history. `context_tokens` means the
model-visible system prompt, bound tool schemas, and message history. The code
and telemetry must not use these names interchangeably.

## Cross-Turn Anchors

Expressions such as after, then, next, `之后`, `然后`, `接着`, and `完成 X 后`
may anchor a new calendar entry to an existing timed entry. Dayboard requires a
search first, then creates through an anchor-aware input:

```text
anchor_entry_id
expected_anchor_updated_at
```

Direct `local_start` and anchor mode are mutually exclusive. In one transaction,
the scheduling service locks and validates the anchor, rejects cancelled,
anytime, missing-end, or stale entries, derives the new start from the current
anchor `end_time`, checks conflicts, and creates the entry. Zero matches do not
write; multiple matches use `ask_clarification`.

Example:

```text
明天上午去跳舞
跳完舞蹈去唱歌

search_calendar_entries(title_query="跳舞", ...)
create_calendar_entry(
  title="唱歌",
  anchor_entry_id=<selected id>,
  expected_anchor_updated_at=<selected updated_at>,
)
```

## Verification

- compact tool-result fixtures stay within explicit token budgets;
- retained ToolMessage history is at least 50 percent smaller than the baseline;
- an ordinary Run does not compact twice;
- emergency compaction remains bounded and preserves atomic tool batches;
- artifacts render live and recover identically after refresh;
- compact search results retain IDs and `updated_at` for mutations;
- the dance-then-sing flow creates singing at the authoritative dance end time;
- user SSE never includes summary or model lifecycle events;
- Northgate comparison by `run_id` reports input, cached, and total tokens, while
  North/Dayboard events report compaction count.

Implementation lands as independent commits: production guardrail, generic North
artifact transport, Dayboard dual-channel tools, North compaction, Dayboard
anchor semantics, dependency upgrade, and final measured verification.
