# Agent Token Optimization History

Status: append-only engineering record  
Last reviewed: 2026-07-20

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

The current fixed surface is 1,515 tokens smaller than the initial baseline and 257 tokens smaller
than the previous 7+1 version. Live input includes provider protocol overhead and user
messages, so it will not equal the offline fixed count.

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
