# Dayboard TODO

Last reviewed: 2026-07-20

## Token Efficiency

- [ ] Establish a programmatic token baseline for representative scheduling commands without
  calling a live model. Track the system prompt, tool schemas, conversation messages, tool results,
  protocol overhead, and each model round separately. The initial `o200k_base` offline estimate is
  1,640 system-prompt tokens plus 2,077 tokens across 11 tool schemas; provider-reported usage
  remains authoritative.
- [x] Keep the long-lived system instructions and tool definitions as a stable request prefix.
  Runtime date/time context must follow static instructions so it does not invalidate cross-Run
  provider prompt caching.
- [ ] Reduce fixed prompt and tool-schema cost only with behavior-contract tests for create, search,
  reschedule, cancel, clarification, multiple commands, and calendar-versus-task classification.
- [ ] Replace message-count-only compaction with a token-aware context budget. Preserve complete
  active AI/tool-call pairs, but summarize or compact completed historical tool payloads before
  they grow into every subsequent model request.
- [ ] Evaluate runtime-supported tool selection or tool-surface redesign. Do not introduce keyword
  routing, hard-coded domain nouns, or a second ad-hoc Agent loop as a token shortcut.
- [ ] Use Northgate's recorded `cached_prompt_tokens` to measure prompt-cache effectiveness by
  Dayboard `run_id`, including the effect of Dayboard's 32-way stable `prompt_cache_key`
  partitioning. Revisit the shard count from measured per-key RPM and hit rates. Keep Northgate
  exact-response caching disabled for requests that can produce write-tool calls.
- [ ] Define and enforce a regression budget for a simple one-write scheduling command after the
  baseline is reproducible. The 2026-07-20 reference Run used 10,362 actual tokens over two calls.

## Gateway Budget Ownership

- [ ] Add Northgate policy scopes for authenticated metadata dimensions, at minimum gateway,
  tenant, user, and model. Policies must have explicit precedence and atomic reservation/settlement.
- [ ] Expose scoped usage, rejection reason, remaining allowance, and reset time through Northgate's
  operator API without logging prompt content.
- [ ] Route all Dayboard production model traffic through Northgate and remove the direct-provider
  fallback before transferring enforcement ownership.
- [ ] Delete Dayboard's provider-token `ProviderBudgetGuard`, Redis counters, and duplicate budget
  configuration after scoped Northgate policies pass integration and failure-path tests.
- [ ] Retain Dayboard's application abuse limits for command frequency, authentication, audio, and
  other product endpoints; those are not provider-budget policies.
- [ ] Remove superseded paths during the migration. The product is still in development, so do not
  preserve compatibility layers for the old budget implementation.
