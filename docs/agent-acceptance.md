# Agent Acceptance

Agent acceptance scenarios are explicit live checks, not part of the normal test suite. They
exercise the deployed HTTP, queue, worker, North runtime, tool, Run-event, and persistence path
with real model calls.

Keep this catalog small and release-oriented. Broad model quality, safety, latency, and token
metrics belong to the versioned [Agent Eval](./agent-eval.md), not to this runner.

The runner is safe by default: without `--execute` it only lists scenarios. Execution also
requires `--allow-writes` because it creates persistent threads, calendar entries, tasks, Runs,
events, and provider usage records. Test titles include a per-thread `验收<tag>` prefix as
explicit title text so repeated catalog runs do not produce ambiguous change targets. Avoid
decorative bracket tags because a model may correctly omit them while inferring a concise title.

```bash
cd apps/api
uv run python scripts/agent_acceptance.py

# Run one scenario against a local stack.
uv run python scripts/agent_acceptance.py \
  --execute --allow-writes \
  --scenario multi-create

# Run the catalog against the production HTTPS API after a deployment batch.
export DAYBOARD_ACCEPTANCE_IDENTIFIER=acceptance-user
export DAYBOARD_ACCEPTANCE_PASSWORD='read-from-a-secret-store'
uv run python scripts/agent_acceptance.py \
  --base-url https://dayboard.selfapi.art \
  --execute --allow-writes
```

Authenticated deployments require a dedicated acceptance account. Supply its username or email
through `DAYBOARD_ACCEPTANCE_IDENTIFIER` (or `--login-identifier`) and its password only through
`DAYBOARD_ACCEPTANCE_PASSWORD`. The runner logs in once and reuses the returned session cookie; it
does not print the password. Keep both values out of committed environment files and shell history,
and load the password from the deployment secret store.

Each turn records terminal status, elapsed time, expected and observed completed tools, missing
tools, result text, Run ID, and thread ID. A non-zero process exit means at least one expectation
failed. A scenario stops after its first failed turn so a failed setup cannot trigger invalid or
costly dependent commands; `skipped_turns` reports the remainder. Use the returned Run ID to
inspect its durable events.

Initial scenarios cover:

- creating separate undated Todo items from vague, unpunctuated action phrases without creating a
  calendar entry or asking for a time;
- mixed calendar/task creation in one message;
- date-only actions creating anytime calendar entries without task fallback or clarification;
- modifying and cancelling multiple calendar entries in one Run (`calendar-changes`);
- completing and changing multiple tasks in one Run (`task-changes`);
- refusing to create a replacement when a change target does not exist.

Add scenarios only for meaningful product behavior or a real regression. Keep wording natural
and assertions focused on durable outcomes rather than exact model prose.
