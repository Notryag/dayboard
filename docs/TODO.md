# Dayboard TODO

Last reviewed: 2026-07-20

## Token Efficiency

- [x] Establish offline and live no-write token baselines for representative scheduling commands.
  The compressed fixed estimate is 897 system-prompt tokens plus 1,797 tokens across 11 schemas;
  live first-round input fell from roughly 4,710 to 2,920 tokens. Continue tracking conversation,
  tool-result, protocol, and per-round growth from provider-reported usage.
- [x] Keep the long-lived system instructions and tool definitions as a stable request prefix.
  Runtime date/time context must follow static instructions so it does not invalidate cross-Run
  provider prompt caching.
- [x] Reduce fixed prompt and schema cost with behavior-contract tests plus real no-write model
  checks for create, search, reschedule, cancel, multiple commands, and calendar-versus-task
  classification. Add clarification and multi-step search-result cases before further compression.
- [x] Replace message-count-only compaction with a token-aware context budget. Preserve complete
  active AI/tool-call pairs, but summarize or compact completed historical tool payloads before
  they grow into every subsequent model request.
- [x] Remove tool schemas from the final confirmation round only after successful terminal writes.
  Search/error/clarification rounds and every new user turn retain the complete tool surface. This
  phase policy adds no classifier call, keyword routing, or parallel Agent loop.
- [ ] Re-evaluate provider-native deferred tool loading when the OpenAI-compatible gateway path
  proves the capability or the product grows beyond the current cohesive 11-tool scheduling set.
  A skill alone does not remove executable schemas, and a model-based selector adds a call.
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
