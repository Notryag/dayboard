# Token Usage Diagnostics

Status: active operational record  
Last reviewed: 2026-07-20

Measured optimization milestones are preserved in
[agent-token-optimization-history.md](./agent-token-optimization-history.md). Append new reductions
there instead of replacing earlier baselines.

## Production Request Path

Production Dayboard model traffic for the configured tenant follows this path:

```text
Dayboard worker
  -> north agent runtime
  -> Northgate Dayboard gateway
  -> OpenAI-compatible provider gateway
  -> model provider
```

Dayboard supplies trusted `tenant_id`, `user_id`, and `run_id` metadata to
Northgate. North owns model-call and tool-call runtime behavior. Dayboard owns
the durable per-Run business usage record. Northgate owns gateway admission,
routing, reservations, attempts, and cross-application traffic diagnostics.

The production environment retains a direct provider URL as rollback
configuration, but both current production tenants are selected into the
Northgate connection. A diagnosis must still verify the selected connection;
the presence of a fallback URL does not prove that a request bypassed Northgate.

## 2026-07-20 Token-Limit Incident

A user submitted one short scheduling command and then received
`TOKEN_LIMIT_EXCEEDED` on the next command. The error came from Northgate policy
admission before another upstream model call. It did not come from Dayboard's
per-user provider budget or from the upstream provider gateway.

The successful Dayboard Run made two model calls:

| Call | Actual input | Actual output | Actual total | Northgate reservation |
| --- | ---: | ---: | ---: | ---: |
| 1 | 5,028 | 40 | 5,068 | 19,852 |
| 2 | 5,272 | 22 | 5,294 | 20,384 |
| Total | 10,300 | 62 | 10,362 | 40,236 |

Northgate estimated each admission as request-body characters divided by three,
plus the configured default maximum output of 4,096 tokens. This conservative
reservation is expected to be replaced with provider-reported actual usage when
the stream finishes.

That settlement did not happen. The two durable Northgate request records were
left as `started`; one attempt was also left as `started`, and the other was
classified as `client_disconnected`. Redis therefore retained both reservations
as active `r:<request_id>` fields and reported `used=40236` against the
Dayboard gateway's 60,000-token daily policy. The next approximately 20,000-token
reservation could not fit, so Northgate correctly enforced incorrect state.

The direct cause is incomplete streaming finalization and policy settlement in
Northgate. Raising Dayboard's separate token budget cannot fix this failure.

## Prompt Size And Cache Findings

The short user message is not the main source of provider input tokens. After
moving runtime context to the end, the current agent sends approximately 7,623
characters of system instructions and 9,094 characters across 11 tool
descriptions and JSON schemas. An offline `o200k_base` count estimates these at
1,640 and 2,077 tokens respectively, or 3,717 fixed tokens before conversation
messages and protocol overhead. Provider-reported usage remains authoritative.
A write command normally requires a second model call after the tool result, so
most fixed context is sent twice when prompt cache is not used.

The first model call used 5,028 input tokens. The post-tool call used 5,272,
only 244 more, which shows that repeated fixed context dominates the second
round rather than the returned tool payload. The system prompt also placed a
microsecond-precision current datetime near the beginning, before nearly all
static rules. That arrangement made the request prefix change on every Run and
prevented the long rule block from being a stable cross-Run cache prefix. The
runtime scheduling context now follows the static rules; its content and
scheduling semantics are unchanged.

The affected thread had 13 messages before its first model call: four human,
six AI, and three tool messages. Their text content totaled 1,091 characters,
including 986 characters of historical tool results, plus approximately 300
characters of historical tool-call arguments. The current write then added 64
characters of tool arguments and a 426-character tool result before the second
model call. This confirms that completed tool payloads are the fastest-growing
part of thread history. North now combines Dayboard's 1,200-token history
threshold with its 40-message hard ceiling using OR semantics. Compaction still
preserves recent complete AI/tool pairs and Dayboard's visible conversation
history remains independent from runtime checkpoints. Summary generation is a
real model call, not free preprocessing; North tags it as
`middleware:summarization` so its usage remains attributable to the same Run
and the threshold can be tuned from measured net savings.

The provider gateway recorded `cached_tokens=0` for both successful calls.
Northgate exact-response caching was also disabled for the Dayboard gateway.
These are separate mechanisms:

- Northgate exact cache reuses an entire identical non-changing request and
  response. Agent calls before and after a tool result are not identical, so it
  is not the primary optimization for this workflow.
- Provider prompt caching may reuse a stable prompt prefix while still executing
  a new completion. No cache-read usage was reported for this Run.

The missing provider prompt-cache hit increases cost and latency, but it did not
cause the 2026-07-20 rejection. The stale Northgate reservation did.

The same `gpt-5.4-mini` compatibility path has reported historical prompt-cache
reads of 3,840 to 5,120 tokens, including traffic through the same upstream
account. The cache accounting path therefore works, but this Run's second call
did not reuse its expected stable prefix. Existing content-minimizing logs cannot
distinguish provider cache admission, upstream routing behavior, or a request
serialization difference. Do not enable Northgate exact-response caching as a
substitute: replaying complete model responses is a poor default for an Agent
whose responses can contain write-tool calls.

The deployed sub2api compatibility path supports `prompt_cache_key` and
automatically derives one when the client omits it. Its current derivation
includes the complete system message and the first user message. Dayboard's
runtime datetime and each new command therefore changed that routing key, even
when requests shared the same long static prefix. Dayboard now supplies an
explicit versioned key for `openai:` models, deterministically partitioned into
32 shards by a hash of trusted tenant/user identity. No raw identity is sent in
the key. This keeps both model calls and later Runs for one user on a stable
cache route while avoiding one global hot key. Northgate continues to record
provider-reported cache reads so the effect can be measured rather than assumed.

## Tool Surface And Prompt Reduction

Dayboard exposes seven scheduling tools plus the runtime interaction tool:

| Area | Tools |
| --- | --- |
| Calendar | `create_calendar_entry`, `search_calendar_entries`, `reschedule_calendar_entry`, `cancel_calendar_entry` |
| Tasks | `create_task_item`, `search_task_items`, `update_task_item` |
| Interaction | `ask_clarification` |

This is one cohesive scheduling surface, not 11 independently loadable plugins. Moving the tool
instructions into a skill would not remove executable JSON schemas from a model request. A tool
selector would also add a model call before most short commands, while provider-native deferred
tool loading is not yet proven across the current OpenAI-compatible gateway path.

Dayboard instead applies deterministic phase-based loading. The first semantic/action round receives
all seven scheduling tools plus `ask_clarification`. A successful calendar search narrows the next
round to four calendar tools plus clarification; a task search narrows it to three task tools plus
clarification. Mixed-domain batches retain the full surface. Successful terminal writes remove
scheduling tools for confirmation. A first malformed/error result restores the full surface; a
second failure in the same user turn removes tools so the model explains the failure instead of
looping. This needs no keyword router or additional model call.

A live no-write comparison used six representative commands: calendar creation, undated task,
deadline task, mixed creation, calendar rescheduling, and task cancellation. All tool calls were
selected by the real model, but none were executed. Compressing repeated policy text while keeping
behavior contracts changed the approximate fixed offline size as follows:

| Fixed input | Initial | Prompt-compressed 11-tool version | Current 7+1 surface |
| --- | ---: | ---: | ---: |
| System prompt | 1,640 | 897 | 903 |
| Tool schemas | 2,077 | 1,797 | 1,556 |
| Total | 3,717 | 2,694 | 2,459 |

The current fixed surface is 33.8% smaller than the initial baseline and 8.7% smaller than the
prompt-compressed 11-tool version. The small system-prompt increase documents unified search and
internal conflict behavior; schema removal more than offsets it.

Provider-reported first-round input fell from 4,707-4,716 tokens to 2,915-2,943 tokens, about
38%. Five compressed-prompt cases initially matched the baseline. The reschedule case exposed a
regression where the destination date was used as the search window; an explicit original-date
rule fixed it, and the focused live rerun selected the correct original date. The final six semantic
routes match the baseline. Repeated calls in each variant reported prompt-cache reads (4,608 before
and 2,560 after), confirming that the smaller stable prefix remains cacheable.

The 7+1 tool surface was then checked with the same six live no-write cases. All routes matched:
calendar creation, undated task creation, deadline task creation, mixed calendar/task calls,
calendar search over the original interval, and task search without `purpose`. Provider-reported
first-round input was 2,805-2,814 tokens, another 101-138 token reduction from the compressed
11-tool version, with 2,560-token cache reads after the first call.

Two live synthetic-result checks exercised the narrowed second round without executing writes. The
calendar 4+1 subset selected `reschedule_calendar_entry` with the authoritative ID,
`expected_updated_at`, and requested destination time using 2,615 input tokens. The task 3+1 subset
selected `update_task_item` with `new_status=cancelled` and `expected_updated_at` using 2,428 input
tokens. This verifies that domain narrowing preserves the mutation path and optimistic-lock field.

An independent live two-round write simulation used synthetic successful tool results and no
database writes. Removing schemas from the final confirmation round reduced its actual input from
4,908 to 3,501 tokens, a 1,407-token saving. Once the no-tools prefix warmed, it reported a 3,328
token cache read. This supports terminal-only pruning without making initial semantic routing less
capable.

## Required Diagnostics

Northgate operator diagnostics should expose, without logging request content:

- lookup by an authenticated metadata dimension such as `run_id`;
- request and provider-attempt outcomes;
- estimated or reserved tokens at admission;
- settled prompt, completion, and total tokens;
- provider-reported cached prompt tokens;
- exact-cache result (`bypass`, `miss`, `hit`, or `error`);
- policy rejection code and remaining/reset headers where applicable.

An MCP server is not the source of truth for this data. The operator HTTP API and
PostgreSQL records must be complete first. A later MCP adapter may wrap those
operator APIs for convenience without receiving database or provider secrets.

## Verification Criteria

The Northgate fix is complete when programmatic tests prove that:

1. A successfully consumed stream settles both request and attempt records.
2. A downstream disconnect settles provider-reported usage when a terminal usage
   event was already observed.
3. A disconnect without authoritative usage remains conservative and does not
   invent actual tokens.
4. Policy reservation fields become settled fields exactly once.
5. Operators can resolve all model calls for one Dayboard `run_id` and distinguish
   reservation, actual usage, provider prompt cache, and exact cache behavior.
