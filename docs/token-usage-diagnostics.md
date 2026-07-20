# Token Usage Diagnostics

Status: active operational record  
Last reviewed: 2026-07-20

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

The short user message is not the main source of provider input tokens. The
current agent sends approximately 7,569 characters of system instructions and
9,109 characters across 11 tool descriptions and JSON schemas. A write command
normally requires a second model call after the tool result, so most of this
fixed context is sent twice.

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
