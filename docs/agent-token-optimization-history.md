# Agent Token Optimization History

Status: append-only engineering record  
Last reviewed: 2026-07-23

This document preserves each measured Dayboard Agent token optimization as a product and
engineering highlight. Do not replace older baselines when a new optimization lands. Append a new
entry with its implementation, semantic acceptance results, provider usage, cache behavior, and
known trade-offs. Provider-reported usage is authoritative; offline `o200k_base` counts compare the
stable system prompt and serialized model-visible tool schemas.

## Baseline Progression

| Version | System prompt | Tool schemas | Fixed total | Change from initial | Live first-round input |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial 11-tool Agent | 1,640 | 2,077 | 3,717 | baseline | 4,707-5,028 |
| Stable-prefix and prompt compression | 897 | 1,797 | 2,694 | -27.5% | 2,915-2,943 |
| Unified 7+1 tool surface | 903 | 1,556 | 2,459 | -33.8% | 2,805-2,814 |
| Absolute temporal classification | 861 | 1,341 | 2,202 | -40.8% | 2,566-2,573 |
| Native anytime calendar entries | 666 | 1,406 | 2,072 | -44.3% | pending deployment sample |
| Compact tool receipts + sequence anchors | 772 | 1,487 | 2,259 | -39.2% | 2,523 |
| Beijing-local protocol + integer versions | 913 | 1,469 | 2,382 | -35.9% | pending deployment sample |

The current fixed surface is 1,335 tokens smaller than the initial baseline. It is 123 tokens larger
than the preceding version because the time protocol explicitly prevents UTC conversion and defines
adjacent-entry behavior. Tool schemas became 18 tokens smaller after integer row versions replaced
timestamp concurrency fields, despite adding a duration parameter. Live input includes provider
protocol overhead and user messages, so it will not equal the offline fixed count.

## 2026-07-20: Incident Baseline

The short scheduling command that triggered investigation used two model calls totaling 10,362
actual tokens. Its calls consumed 5,028 and 5,272 input tokens. The original stable input consisted
of about 1,640 system-prompt tokens and 2,077 tokens across 11 tool schemas before messages and
protocol overhead. Completed tool payloads also accumulated in thread history.

This baseline exposed three independent problems: stale Northgate reservations caused a false daily
limit rejection, a dynamic datetime near the start of the prompt prevented stable-prefix reuse, and
the full fixed surface was resent for post-tool confirmation.

## 2026-07-20: Stable Prefix, Cache Routing, And History Bounds

Runtime date context moved after static instructions. Dayboard added a stable, versioned 32-way
`prompt_cache_key`, partitioned by a hash of trusted tenant/user identity. North added token-aware
history compaction at 1,200 tokens with a 40-message ceiling and tagged summary-model usage.

Historical provider records had shown cache reads of 3,840-5,120 tokens. Live warm checks after the
change reported cache reads of 4,608 tokens on the 11-tool surface. This established that the
OpenAI-compatible path and Northgate usage accounting could observe provider prompt caching.

## 2026-07-20: Prompt And Schema Compression

Repeated policy text was consolidated: the system prompt owns cross-tool behavior and schemas own
field constraints. Fixed input fell from 3,717 to 2,694 tokens, a 27.5% reduction. Six real no-write
semantic cases reduced first-round provider input from about 4,710 to 2,915-2,943 tokens.

The first compressed run exposed a real regression: rescheduling searched the destination date
instead of the original entry date. Restoring one explicit original-date rule fixed the route. This
is why prompt reductions require live semantic comparisons rather than token counts alone.

Successful terminal writes also began removing all tool schemas from the final confirmation round.
A live synthetic-result comparison reduced that round from 4,908 to 3,501 input tokens, saving
1,407 tokens. The warmed no-tools variant reported a 3,328-token cache read.

## 2026-07-20: Unified 7+1 Tool Surface And Domain Binding

Dayboard removed separate calendar/task list tools and the conflict-check tool. Empty bounded
searches now list objects, exact calendar intervals use overlap semantics for availability, and
calendar writes check conflicts internally. Search `purpose`, task-create `status`, duplicate result
IDs, and constant `requires_follow_up=false` fields were removed. Trusted timezone and Run/idempotency
fields remain runtime-owned.

The initial surface is seven scheduling tools plus `ask_clarification`. A successful search narrows
the next model round to its domain plus clarification; mixed-domain batches remain full, terminal
writes remove tools, and one failed result restores the full surface before a second failure stops
tool retries.

Fixed input fell again from 2,694 to 2,459 tokens, an 8.7% reduction over the previous version and
33.8% from the initial baseline. The same six live no-write cases used 2,805-2,814 first-round input
tokens and retained 2,560-token cache reads. Real synthetic-result second rounds correctly selected
calendar rescheduling with the 4+1 subset at 2,615 input tokens and task cancellation with the 3+1
subset at 2,428 input tokens. Both retained `expected_updated_at`; neither executed a write.

## 2026-07-20: Absolute Temporal Classification

Calendar/task classification was made deliberately mechanical: any resolvable date, clock, or
daypart creates a calendar entry, including completion and deadline wording. Only actions with no
resolvable temporal anchor become tasks. Date-only actions use the existing 09:00 calendar default.

To keep schemas consistent with this rule, Agent task creation now accepts only `title`; task updates
accept title or status and cannot add a due time. Domain due fields remain available to the schedule
API and stored data, but the Agent cannot create a contradictory timed task.

Fixed input fell from 2,459 to 2,202 tokens, a 10.5% reduction for this step and 40.8% from the
initial baseline. Six real no-write cases used 2,566-2,573 input tokens. They verified that
"明天提交报告", "明天早上8点前吃药", and "明天买牛奶" create calendar entries; "提交报告" and
"晚点整理资料" create tasks; and a mixed message emits both calls. Warm requests reported 2,048
cached input tokens. No write tool was executed.

## 2026-07-20: Native Anytime Calendar Entries

Date-only calendar actions now use a first-class `anytime` shape with `scheduled_date`, rather than
inventing a 09:00 clock. Clock/daypart actions remain `timed`; vague expressions still become
undated tasks. Anytime entries have no clock reminder and do not participate in overlap conflicts.

The prompt was reduced to semantic classification, execution, search-before-change, clarification,
and response rules. Persistence defaults and invariants remain in schemas and services. The prompt
fell from 861 to 666 tokens. The create schema gained the explicit date/time union, increasing the
model-visible schemas by an estimated 65 tokens to 1,406. Fixed input therefore fell from 2,202 to
2,072 tokens, a 5.9% reduction for this step and 44.3% from the initial baseline. Provider input and
cache-read measurements remain to be recorded after deployment.

## 2026-07-22: Compact Tool Results And Sequence Anchors

Scheduling tools now split each result into compact model-visible content and a complete validated
presentation artifact. Fixed prompt/schema cost is unchanged by this transport split. A
representative production calendar-create payload fell from 181 to 136 `o200k_base` tokens (24.9%)
without removing the ID, timing, status, version, or reminder data needed for later reasoning. The
complete entity remains available to live SSE and refresh recovery without entering model context.
The broader 50% ToolMessage-history target is measured after Run-aware compaction, not claimed for
every individual receipt shape.

Cross-turn sequence semantics then added `anchor_entry_id` and `expected_anchor_updated_at` to
calendar creation. The server locks and validates the selected entry and derives the new start from
its authoritative end time. Prompt cost rose from 666 to 772 tokens and the eight model-visible
schemas rose from 1,406 to 1,487, for a fixed total of 2,259. This is a 9.0% increase over the
previous fixed surface but still 39.2% below the initial 3,717-token baseline. The added cost buys
correct handling of cases such as `跳完舞蹈去唱歌` without copying a stale end time through the
model. The deployed provider and compaction measurements are recorded below.

The deployed two-turn acceptance created a 09:00-10:00 dance entry, then searched it and created
singing at exactly 10:00-11:00. The first Run used two model calls totaling 4,468 input and 63
output tokens; its first round used 2,523 input tokens. The anchored second Run required three
semantic calls (search, create, confirmation), totaling 8,370 input and 174 output tokens. It
produced zero summarization events, eliminating the previous duplicate-compaction failure mode.

Northgate correlated all five requests by Run. It reported 1,536 cached prompt tokens on the first
call of the second Run. The provider omitted cached-token detail on the other four calls, which
Northgate surfaced as `CACHED_USAGE_MISSING`; therefore 1,536 is a measured lower bound, not a zero
cache result. `EXACT_CACHE_BYPASSED` was also expected because each semantic round had different
messages or bound tools and was not an identical request replay.

## 2026-07-23: Beijing-Local Model Protocol And Integer Versions

The model-visible scheduling contract now uses only Beijing local wall-clock values in
`YYYY-MM-DDTHH:mm`. UTC instants remain in PostgreSQL and presentation artifacts. Provider-bound
ToolMessages discard artifacts, legacy absolute receipts are rewritten defensively, and the new
`dayboard-time-v2` checkpoint namespace prevents old UTC receipts from entering either summary or
main-model context. Duration edits use `new_duration_minutes`, so the model no longer computes an
end timestamp.

Calendar and task concurrency moved from `expected_updated_at` to an atomic integer `row_version`.
The system prompt increased from 772 to 913 tokens to make the local-time and adjacency invariants
explicit. The eight model-visible schemas fell from 1,487 to 1,469 tokens, producing a fixed total
of 2,382 tokens: 5.4% above the preceding version and still 35.9% below the initial 3,717-token
baseline. Provider input and cache-read measurements remain pending deployment.

Programmatic regression coverage verifies UTC storage/local receipts, artifact isolation, stale
version rejection, anchor validation, and shortening a 16:00-17:00 entry to 30 minutes without
moving the independent 17:00 entry.

## 2026-07-23: Deterministic Terminal Completion

Successful terminal scheduling writes now end the Agent loop in Dayboard middleware with a short
grounded completion assembled from canonical ToolMessages. The model is still called after searches,
errors, partial results, or unresolved work, but it is no longer called merely to restate a committed
write already rendered by the UI. The fixed system-prompt and tool-schema surface remains 2,382
tokens; this change removes an entire provider round instead of compressing that round.

The pre-change production sample contained four final confirmation calls totaling 10,144 prompt
tokens and 55 completion tokens. Their 10,199 total tokens were 29.4% of the 34,638 tokens consumed
by four Runs. Post-deployment provider measurements remain to be recorded before claiming realized
savings.

## Entry Template

Append future optimizations with:

```text
## YYYY-MM-DD: Change Name

Implementation:
Offline fixed tokens before/after:
Provider input/output before/after:
Prompt-cache reads:
Semantic acceptance cases:
Regressions found and corrected:
Trade-offs or follow-up work:
```
