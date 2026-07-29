# Agent Token Optimization History

Status: append-only engineering record  
Last reviewed: 2026-07-27

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
| Model-only system rules | 829 | 1,469 | 2,298 | -38.2% | pending deployment sample |
| Late-bound runtime time context | 763 | 1,469 | 2,232 | -40.0% | 7,227; 6,656 cached when warm |

The current stable fixed surface is 1,485 tokens smaller than the initial baseline. The separate
runtime context adds about 67 dynamic tokens per request, so this latest step improves prefix
stability rather than materially reducing uncached input. Tool schemas became 18 tokens smaller
after integer row versions replaced timestamp concurrency fields, despite adding a duration
parameter. Live input includes runtime context, provider protocol overhead, and user messages, so it
will not equal the offline fixed count.

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

## 2026-07-24: First Post-v0.3.21 Admin Cache Sample

Northgate CLI measured `admin` traffic from 09:00 through 17:01 Asia/Shanghai and found one
correlated request for Run `79f86d9a-aa4d-40c4-bb54-93bc592f365d`. Dayboard and Northgate agreed
on one model call: 3,954 prompt tokens, 6 completion tokens, and 3,960 total tokens. The Run had no
tool events, no retry/fallback attempt, and no compaction event. This confirms that the earlier
multi-call and repeated-summarization failure was not present in this sample.

The fixed prompt/schema baseline remained 2,382 tokens, leaving about 1,572 tokens for bounded
conversation/runtime context. The authoritative Conversation contained 134 older persisted
messages and no persisted summary, but the North checkpoint namespace supplies a bounded runtime
state; the durable message count is not evidence that all 134 messages entered this request. The
3,954-token prompt remained below the 6,000-token normal compaction threshold.

Prompt-cache reads remain unknown rather than zero. The provider omitted cached-prompt detail, so
Northgate reported `CACHED_USAGE_MISSING` and labelled the 0% cache ratio as a lower bound. This
single sample cannot prove whether the 32-way stable `prompt_cache_key` partition helped or hurt.
Exact response caching was bypassed as expected for a semantic Agent request.

Northgate reserved 12,676 tokens and released 8,716 after the 3,960-token settlement, an
estimate-to-actual ratio of 3.201. Reservation is temporary admission capacity, not provider token
consumption. Correlation metadata was present but classified as `legacy`; trusted dynamic metadata
migration remains a separate Northgate prerequisite.

## 2026-07-27: Model-Only System Rules

The system prompt now contains only decisions and response behavior that the model must perform.
Descriptions of internal conflict checking, PostgreSQL/UTC artifact ownership, trusted-context
injection, and low-level tool failure handling were removed. Time classification, Beijing-local
tool inputs, sequence references, search-before-change, clarification, optimistic-version
selection, and grounded confirmations remain because code cannot choose those semantics for the
model.

The system prompt fell from 913 to 829 `o200k_base` tokens, a 9.2% prompt reduction. The eight
model-visible schemas remain 1,469 tokens, so fixed input fell from 2,382 to 2,298 tokens, a 3.5%
reduction for this step and 38.2% from the initial 3,717-token baseline. Provider usage and semantic
acceptance measurements remain pending deployment.

## 2026-07-27: Late-Bound Beijing Runtime Context

The minute-level Beijing datetime, locale, and relative-date table no longer live in the stable
system prompt. Dayboard captures them once when a Run creates its Agent and injects the resulting
trusted `SystemMessage` immediately before the latest user message for every model call in that
Run. The context is not persisted in conversation history, remains identical across tool rounds in
one Run, and is injected for every command rather than relying on incomplete relative-time keyword
detection.

The stable system prompt is 763 `o200k_base` tokens, down from 829. The runtime context is about 67
tokens for a typical `zh-CN` request, so this split primarily improves prefix structure rather than
removing the required time context. Stable instructions and prior conversation can form a reusable
prefix while the minute-varying context stays near the current command.

The deployed `context-01` Eval passed both create and contextual-reschedule turns with exact tool
behavior. Its cold Run used 22,189 input and 210 output tokens over three model calls; Northgate saw
the upstream cache detail omitted on all three. A second Eval after propagation used 22,201 input
and 215 output tokens. All three calls then reported 6,656 cached prompt tokens, for 19,968 cached
tokens and an exact 89.94% prompt-cache ratio. At the configured `$1.00/M` input, `$0.10/M` cached
input, and `$6.00/M` output prices, the warm Eval cost `$0.005521`; the same usage without prompt
caching would cost about `$0.023491`, a 76.5% reduction.

A third Eval at 16:18, across the minute boundary from the 16:16 warm sample, again passed both
turns. Northgate reported one 6,656-token cache read and saw the provider omit cache detail on the
other two calls. This proves that changing the injected minute no longer prevents the stable prefix
from being reused; it does not prove that every request hits, because omitted usage remains unknown.

Compared with the immediately preceding production sample, the cold deployed input fell from
22,669 to 22,189 tokens, a 480-token or 2.1% reduction across three model calls. Dayboard's Eval
event projection still reported cached usage as unknown even when Northgate recorded all three
cache hits, so cached-token propagation into Run events remains a separate observability defect.

## 2026-07-27: Cached Usage Event Projection

North Runtime now preserves provider cache reads from direct cached-token fields and from the
LangChain/OpenAI `input_token_details.cache_read` and `prompt_tokens_details.cached_tokens` shapes.
It emits the normalized value as `cached_input_tokens`; omission remains `None` rather than an
invented zero. Dayboard's existing typed Run-event extension and Eval aggregation can therefore
consume the value without a second provider-specific parser.

North regression tests cover the complete `LLMResult -> AIMessage.usage_metadata -> RuntimeJournal`
path, and the deployed Worker normalized a synthetic 100-input/80-cache payload to
`cached_input_tokens=80`. Two immediate post-deployment production Evals were not positive cache
samples because Northgate independently confirmed that the upstream omitted cache detail on all
six calls. Dayboard correctly kept those values unknown. A future naturally reported cache read
must be compared between the Eval report and Northgate to complete live positive-path validation.

## 2026-07-28: v0.3.22 Positive Cache And Cost Baseline

The deployed `context-01` Eval again passed the create and contextual-reschedule turns with the
exact expected tools. Three model calls used 6,336 input and 193 output tokens, or 6,529 total.
Every call reported provider cache detail through North and Dayboard: 4,608 cached input tokens,
for an exact 72.73% prompt-cache ratio. Northgate independently recorded the same values from
`prompt_tokens_details.cached_tokens` and priced all three requests.

Northgate charged 3,348 microdollars, or `$0.003348`. The first create Run used 2,011 input and 58
output tokens, including 1,536 cached input tokens, and cost `$0.000977`. The two-call contextual
reschedule Run used 4,325 input and 135 output tokens, including 3,072 cached input tokens, and cost
`$0.002371`. Exact-response caching remained bypassed as intended; these are provider prompt-cache
reads, not replayed model responses.

Compared with the previous warm `context-01` sample, total tokens fell from 22,416 to 6,529
(`70.9%`) and exact cost fell from `$0.005521` to `$0.003348` (`39.4%`). The cost reduction is
smaller than the token reduction because the prior sample had a higher prompt-cache ratio. The new
Eval budget records the measured one-write baseline and fails `context-01` when its first turn
exceeds 2,500 total tokens, leaving about 20.8% headroom over the 2,069-token result.

## 2026-07-29: v0.3.25 Clarification CAS Baseline

The deployed `same-01` Eval passed setup, same-name option projection, typed clarification,
state-version CAS submission, continuation cancellation, interaction consumption, and final
scheduled/cancelled REST Oracle assertions at 100%. The complete four-Run flow used 21,315 input
and 362 output tokens, or 21,677 total, across six model calls.

The two fixture creation Runs used 2,919 and 3,287 tokens. The continuation cancellation used 4,167
tokens. The clarification Run was the outlier at 11,304 tokens across three calls: search, the model
decision to call `ask_clarification`, and an unnecessary model call after that tool. The redundant
third call alone used 3,932 input and 49 output tokens. Cache detail was missing on three of the six
calls. Northgate measured at least 6,656 cached input tokens and priced three calls at 6,330
microdollars (`$0.006330`); both values are lower bounds because the remaining three calls omitted
cache detail and price settlement. The exact aggregate cost remains unknown rather than being
reported as zero.

North's `ClarificationMiddleware` currently records the typed request with a LangGraph `Command`
but does not terminate the graph. [north-agent#1](https://github.com/Notryag/north-agent/issues/1)
now includes this production evidence and a regression requirement that `ask_clarification` end the
current Run without losing the typed outcome. After that fix, rerun `same-01` and compare model-call
count, tokens, latency, and exact Northgate cost against this baseline.

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
