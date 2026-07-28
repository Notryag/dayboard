# Agent Eval

Agent Eval is the quantitative live-model benchmark. It is separate from deterministic CI and
the small deployment Acceptance catalog:

- CI proves domain, persistence, tool schema, tenant isolation, Run lifecycle, Reminder Outbox,
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
forbidden tools.

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

## One-time production authentication setup

Create a dedicated Eval account and obtain its tenant and user IDs once. Do not point Eval at a
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
DAYBOARD_EVAL_TENANT_ID=<dedicated Eval tenant UUID>
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
forbidden-tool violation rate, clarification accuracy, category accuracy, latency p50/p95, and
complete setup-plus-evaluated-turn token totals. Token metrics include input, output, total,
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
provider availability.
