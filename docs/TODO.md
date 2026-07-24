# Dayboard TODO

Last reviewed: 2026-07-24

## Agent Platform Extraction

- [x] Replace unversioned durable Run `event_metadata` with an optional platform-owned
  `EventExtensionEnvelope { kind, schema_version, payload }`. Keep generic lifecycle fields in the
  Run event itself; require Dayboard or the runtime adapter to name and validate extension payloads
  that are persisted for diagnostics or replay.
- [x] Split generic Run execution coordination from Dayboard's Agent construction, scheduling
  result projection, user-visible progress projection, usage settlement, and StreamBridge adapter.
- [x] Delete the superseded orchestration path while splitting `apps/api/src/dayboard/app/commands.py`;
  do not retain a compatibility wrapper for the old execution flow.
- [x] Define the product-neutral `RunExecutionDriver` callback port in Agent Platform. Keep the
  North implementation and Dayboard result projector in Dayboard, so Platform has no dependency on
  North or scheduling concepts. Queue jobs carry only `run_id`; workers restore trusted execution
  context and input from PostgreSQL.
- [x] Decide whether to extract reusable PostgreSQL Conversation/Run adapters now. Keep them in
  Dayboard: one product is not evidence for a shared schema or migration package, and Platform must
  not import North merely to mirror the runtime.
- [ ] Re-evaluate an optional Platform SQLAlchemy adapter only after a second product proves the
  same schema, tenant, transaction, and lifecycle contract. Generalize a North adapter only after a
  second product proves a common runtime contract; Platform must not import North today.
- [ ] Make Platform `PendingInteraction` the only durable clarification authority. North graph
  state may signal one Run, but the Dayboard driver must eventually receive one structured outcome
  rather than interpreting a second persisted clarification representation.
- [ ] Evaluate provider usage accounting and notification delivery as later platform capabilities
  only when their lifecycle boundaries are stable or a second product needs them.

The Event Extension Envelope and Run execution coordination slices are complete. Migration
squashing remains deferred until every persistent environment has reached Alembic revision
`202607230007` or later.

## Architecture Hardening

- [x] Introduce a Dayboard-owned Scheduling Unit of Work with storage-neutral calendar, task, and
  reminder scheduling ports. Return domain objects from repositories, keep ORM mapping in `db`, and
  remove the `SchedulingService(session)` path.
- [x] Move scheduling transaction ownership to the outer API and serialized Agent tool boundaries.
  Calendar/task writes and Reminder Outbox replacement now commit or roll back together; focused
  tests cover hidden-commit prevention and reminder-failure rollback.
- [x] Move Reminder inbox/delivery lifecycle behind explicit application ports and its own Unit of
  Work. Keep `read_at` separate from delivery status, distinguish `expired` from `cancelled`, and
  project current source title/time/status into the inbox. Do not combine this lifecycle into
  Scheduling merely because both use the current database.
- [x] Move Voice persistence behind explicit application ports as a separate vertical slice.
- [x] Move Account Recovery persistence behind Dayboard-owned ports and a Unit of Work. Keep raw
  reset tokens out of storage, serialize issue/confirm/login through the User row, and leave mail
  delivery outside the database transaction.
- [x] Move Provider Usage behind typed application ports and an independent Unit of Work. Enforce
  owner-scoped idempotent insertion, return storage-neutral aggregates, and keep settlement or Redis
  reconciliation failures from replacing the authoritative Run outcome.
- [x] Move the Scheduling composition root out of `dayboard.app` into the explicit outer
  `dayboard.composition` package without retaining an import wrapper.
- [x] Move the Platform and Run composition roots out of `dayboard.app`. The storage-free
  CommandService and Run driver no longer construct FastAPI, SQLAlchemy, Settings, or runtime
  adapters. The FastAPI dependency, per-Run North driver, fresh runtime-event UoW factory, and Worker
  wiring now meet only through explicit `dayboard.composition` modules; no old import wrapper remains.

## Token Efficiency

- [x] Implement compact ToolMessage receipts, validated presentation artifacts, Run-aware
  compaction, atomic tool-batch retention, and concurrency-safe cross-turn anchors from
  `context-token-optimization.md`.
- [x] Measure the deployed sequence flow by Run through Northgate and record input, output, cached
  lower bound, and zero compaction events in `agent-token-optimization-history.md`.

- [x] Establish offline and live no-write token baselines for representative scheduling commands.
  The current fixed estimate is 913 system-prompt tokens plus 1,469 tokens across seven scheduling
  schemas and `ask_clarification`. The last pre-anytime live first-round sample was 2,566-2,573
  tokens, down from about
  4,710 initially, 2,915-2,943 after prompt compression, and 2,805-2,814 after tool unification.
  Continue tracking conversation, tool-result, protocol, and per-round growth from provider usage.
- [x] Keep the long-lived system instructions and tool definitions as a stable request prefix.
  Runtime date/time context must follow static instructions so it does not invalidate cross-Run
  provider prompt caching.
- [x] Reduce fixed prompt and schema cost with behavior-contract tests plus real no-write model
  checks for create, search, reschedule, cancel, multiple commands, and calendar-versus-task
  classification. Add clarification and multi-step search-result cases before further compression.
- [x] Replace message-count-only compaction with a token-aware context budget. Preserve complete
  active AI/tool-call pairs, but summarize or compact completed historical tool payloads before
  they grow into every subsequent model request.
- [x] Bind tools by canonical result phase: full 7+1 surface initially, same-domain tools plus
  clarification after search, full surface for mixed batches or one recovery attempt, and no tools
  after terminal writes or a second failure. This adds no classifier call, keyword routing, or
  parallel Agent loop.
- [ ] Re-evaluate provider-native deferred tool loading when the OpenAI-compatible gateway path
  proves the capability or the product grows beyond the current cohesive seven-tool scheduling set.
  A skill alone does not remove executable schemas, and a model-based selector adds a call.
- [ ] Use Northgate's recorded `cached_prompt_tokens` to measure prompt-cache effectiveness by
  Dayboard `run_id`, including the effect of Dayboard's 32-way stable `prompt_cache_key`
  partitioning. Revisit the shard count from measured per-key RPM and hit rates. Keep Northgate
  exact-response caching disabled for requests that can produce write-tool calls.
- [ ] Define and enforce a regression budget for a simple one-write scheduling command after the
  baseline is reproducible. The 2026-07-20 reference Run used 10,362 actual tokens over two calls.

## Gateway Budget Ownership

Northgate prerequisite: [northgate#3](https://github.com/Notryag/northgate/issues/3) tracks trusted
tenant/user attribution and scoped policy enforcement. Its current gateway-wide policy is only a
global cost guard, not a replacement for a Dayboard user budget.

- [ ] Add signed, trusted dynamic tenant and user attribution to Northgate. Correlation metadata
  alone must never authorize a policy scope.
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

## Background Reminder Delivery

- [ ] Define a Dayboard Web Push contract before implementation: device-scoped subscriptions,
  VAPID credentials, source deep links, subscription revocation, and per-subscription delivery
  attempts must be independent from the existing in-app reminder delivery state.
- [ ] Add a narrow Web Push vertical slice: manifest and Service Worker, authenticated subscribe /
  unsubscribe APIs, durable subscription and attempt records, Worker delivery after a short claim
  transaction, invalid-subscription cleanup, and notification-click navigation to the source item.
- [ ] Keep foreground browser Notifications as an optional in-app enhancement. Do not present them
  as installed-PWA background delivery.
