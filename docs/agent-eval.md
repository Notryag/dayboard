# Agent Eval

Agent Eval is the quantitative live-model benchmark. It is separate from deterministic CI and
the small deployment Acceptance catalog:

- CI proves domain, persistence, tool schema, user isolation, Run lifecycle, Reminder Outbox,
  API, and browser behavior without spending model tokens.
- Acceptance runs a few end-to-end deployed-stack scenarios after a release.
- Agent Eval measures model behavior over a broad, versioned Chinese scheduling corpus.

The committed corpus is `apps/api/evals/agent_eval.json`, and the installed runner command is
`dayboard-eval`. The corpus contains 128 cases: eight cases in
each of 16 categories covering relative dates, clock times, time periods, deadlines, calendar/task
classification, multiple actions, unpunctuated voice transcripts, modifications, cancellations,
same-name ambiguity, typos, contextual references, conflicts, missing targets, foreign timezones,
and privilege/prompt-injection attempts. Cases may contain setup turns and multiple evaluated
turns. Every evaluated turn declares exact expected tool counts, expected terminal status, and
forbidden tools. Measured critical turns may also assert the schedule state returned by the normal
user-scoped REST API, so calling the right tool with the wrong title, date, time, or status fails.

Schedule assertions use a small product-level contract:

```json
{
  "message": "明天九点创建「会议{tag}」",
  "expected_tools": {"create_calendar_entry": 1},
  "expected_schedule": [{
    "kind": "calendar",
    "title": "会议{tag}",
    "status": "scheduled",
    "timing_kind": "timed",
    "local_start": "{tomorrow}T09:00",
    "local_end": "{tomorrow}T10:00"
  }]
}
```

The Oracle reads PostgreSQL-backed `/api/calendar-entries` or `/api/task-items` projections and
normalizes aware timestamps into each entity's local timezone before comparing them. It does not
trust model receipts or assistant text. Supported execution-scoped templates are `{tag}`, `{today}`,
`{tomorrow}`, `{day_after_tomorrow}`, `{future_date}`, and `{future_month_day_zh}`. The Runner
captures them once at startup so a long Eval cannot drift across midnight. Prefer these templates
over calendar literals that eventually move into the past.

The runner is read-only by default:

```bash
cd apps/api

# Validate and summarize the corpus without model calls.
uv run dayboard-eval

# Run a low-cost category sample against a local stack.
uv run dayboard-eval \
  --execute \
  --category classification \
  --limit 8 \
  --output eval-report.json

# Measure a small critical case three times; repeating the full corpus is rejected.
uv run dayboard-eval \
  --execute \
  --case context-01 \
  --repeat 3 \
  --output eval-stability.json

# Run the full authenticated benchmark after the one-time token setup below.
export DAYBOARD_EVAL_BASE_URL=https://dayboard.selfapi.art
uv run dayboard-eval \
  --execute \
  --min-accuracy 0.85 \
  --output eval-report.json
```

`--execute` is the explicit write boundary because every case gets an isolated persistent Thread.
Use `--case`, `--category`, and `--limit` while developing to control cost. Every invocation creates
a unique execution ID and includes it in Thread titles, idempotency keys, and the report, so the same
case can be rerun without a `409` conflict.
When authenticated by the dedicated Eval Token, the Runner first cancels that identity's still-active
calendar entries and tasks through the normal CAS-protected product APIs. This keeps earlier Eval
runs from introducing unrelated conflict results while retaining their history. Password-login
fallback never performs this reset. Use `--preserve-active-schedule` only when a scenario deliberately
needs existing Eval-user data.
Repeated attempts use separate Threads and idempotency namespaces. `--repeat` is capped at 10 and
requires an explicit `--case`, preventing accidental multiplication of the complete paid benchmark.

Setup steps use the same evaluator as measured turns rather than acting as unverified fixture
creation. A turn may also declare a `clarification` contract that validates the persisted option
presentation, submits the selected option with the returned state version, waits for the continuation
Run, verifies its tools and schedule state, and finally proves the interaction was consumed. This
tests the product's durable CAS-resume path rather than accepting an assistant question as success.

## One-time production authentication setup

Create a dedicated Eval account and obtain its user ID once. Do not point Eval at a
normal user or admin identity. Generate a token locally and store only its digest on the Dayboard
server:

```bash
install -d -m 700 ~/.config/dayboard-eval
umask 077
openssl rand -hex 32 | tr -d '\n' > ~/.config/dayboard-eval/token
sha256sum ~/.config/dayboard-eval/token
```

Configure the API container with all three values and recreate it:

```text
DAYBOARD_EVAL_AUTH_TOKEN_SHA256=<sha256 hex digest>
DAYBOARD_EVAL_USER_ID=<dedicated Eval user UUID>
```

The runner automatically reads `~/.config/dayboard-eval/token`. Override the path with
`DAYBOARD_EVAL_TOKEN_FILE` or `--token-file`. The file must be regular, non-empty, no larger than
4 KiB, and inaccessible to group and other users. `DAYBOARD_EVAL_TOKEN` is available for CI secret
injection but must not be committed or placed in shell history.

Password login remains an explicit fallback for transitional environments through
`DAYBOARD_EVAL_IDENTIFIER` plus `DAYBOARD_EVAL_PASSWORD`; it cannot be combined with token
authentication. Raw tokens and passwords are never included in reports.

The JSON report contains exact case accuracy, status accuracy, tool precision/recall/F1,
forbidden-tool and response-safety violation rates, schedule-assertion accuracy, clarification
accuracy, category accuracy, latency p50/p95, and complete setup-plus-evaluated-turn token totals.
Response safety uses per-case forbidden substrings for concrete prompt-leak and false-success claims;
it does not infer safety from assistant tone. Each setup and turn
records its `run_id`, while the report records the fixed template context used for date resolution.
Token metrics include input, output, total,
model-call count, mean/p50/p95, cached input, missing-cache-detail calls, and prompt-cache percent.
Cached input and cache percent are `null` whenever any provider call omits cache details; unknown
cache usage is never reported as zero. Monetary cost remains Northgate-owned because it depends on
the effective provider/model price version. A measured turn may define `max_total_tokens`; exceeding
it sets `token_budget_match=false`, fails the case, and contributes to
`token_budget_violation_rate`. Do not add a budget without a reproducible deployed baseline and
reasonable variance headroom. The process exits non-zero when exact case accuracy is below
`--min-accuracy`. Store reports as build artifacts or external benchmark history; do not commit
reports containing production Thread or Run IDs.

Corpus structure and metric calculation run in normal CI. Full live-model execution stays an
explicit release or model-change gate because it writes data, costs tokens, and may be affected by
provider availability. Versioned category gates are stricter than the overall CLI threshold:
security, classification, modification, and cancellation currently require 100%, and any failed
category gate makes the process exit non-zero.
