# Agent Eval

Agent Eval is the quantitative live-model benchmark. It is separate from deterministic CI and
the small deployment Acceptance catalog:

- CI proves domain, persistence, tool schema, tenant isolation, Run lifecycle, Reminder Outbox,
  API, and browser behavior without spending model tokens.
- Acceptance runs a few end-to-end deployed-stack scenarios after a release.
- Agent Eval measures model behavior over a broad, versioned Chinese scheduling corpus.

The committed corpus is `apps/api/evals/agent_eval.json`. It contains 128 cases: eight cases in
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
uv run python scripts/agent_eval.py

# Run a low-cost category sample against a local stack.
uv run python scripts/agent_eval.py \
  --execute --allow-writes \
  --category classification \
  --limit 8 \
  --output eval-report.json

# Run the full authenticated benchmark.
export DAYBOARD_EVAL_IDENTIFIER=eval-user
export DAYBOARD_EVAL_PASSWORD='read-from-a-secret-store'
uv run python scripts/agent_eval.py \
  --base-url https://dayboard.selfapi.art \
  --execute --allow-writes \
  --min-accuracy 0.85 \
  --output eval-report.json
```

`--execute` also requires `--allow-writes` because every case gets an isolated persistent Thread.
Passwords are accepted only through `DAYBOARD_EVAL_PASSWORD` and are never included in reports.
Use `--case`, `--category`, and `--limit` while developing to control cost.

The JSON report contains exact case accuracy, status accuracy, tool precision/recall/F1,
forbidden-tool violation rate, clarification accuracy, category accuracy, latency p50/p95, and
token mean/p50/p95. The process exits non-zero when exact case accuracy is below
`--min-accuracy`. Store reports as build artifacts or external benchmark history; do not commit
reports containing production Thread or Run IDs.

Corpus structure and metric calculation run in normal CI. Full live-model execution stays an
explicit release or model-change gate because it writes data, costs tokens, and may be affected by
provider availability.
