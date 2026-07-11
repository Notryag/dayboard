# Agent Acceptance

Agent acceptance scenarios are explicit live checks, not part of the normal test suite. They
exercise the deployed HTTP, queue, worker, North runtime, tool, Run-event, and persistence path
with real model calls.

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
uv run python scripts/agent_acceptance.py \
  --base-url https://www.selfapi.art/dayboard-api \
  --execute --allow-writes
```

Each turn records terminal status, elapsed time, expected and observed completed tools, missing
tools, result text, Run ID, and thread ID. A non-zero process exit means at least one expectation
failed. A scenario stops after its first failed turn so a failed setup cannot trigger invalid or
costly dependent commands; `skipped_turns` reports the remainder. Use the returned Run ID to
inspect its durable events.

Initial scenarios cover:

- mixed calendar/task creation in one message;
- modifying and cancelling multiple calendar entries in one Run (`calendar-changes`);
- completing and changing multiple tasks in one Run (`task-changes`);
- refusing to create a replacement when a change target does not exist.

Add scenarios only for meaningful product behavior or a real regression. Keep wording natural
and assertions focused on durable outcomes rather than exact model prose.
