# ADR-004 Adopt Callback-First Token Accounting

## Status

Accepted

## Context

Dayboard needs accurate provider usage for cost visibility, tenant budgets, and future
billing. Model usage is a runtime fact, but tenant attribution, pricing, persistence, and
budget policy are product concerns.

Reading usage only from the final LangGraph state is incomplete because intermediate model
calls can select tools, perform clarification, or fail before a final message is produced.
Putting basic counting in agent middleware would also mix observation with execution state
and could make accounting depend on message rewriting.

DeerFlow uses a callback-based RunJournal as the authoritative observer, persists Run usage
from the worker finalization path, and reserves middleware for step attribution and active
budget enforcement. Dayboard should follow the same boundary while its runtime remains
simpler and has no subagents.

## Decision

Use the following ownership model:

```text
provider model call
  -> LangChain callback
  -> north.RuntimeJournal emits model.completed
  -> north normalizes provider usage
  -> north.RuntimeUsageAccumulator deduplicates by call_id
  -> Dayboard finalizes the Run
  -> Dayboard persists one provider usage summary for the Run
  -> Dayboard applies tenant budgets, pricing, and reconciliation
```

North owns:

- observing every model call through callbacks;
- normalizing common provider fields to `input_tokens`, `output_tokens`, and
  `total_tokens`;
- deriving `total_tokens` when a provider omits it;
- deduplicating repeated callback delivery by model call ID;
- exposing product-neutral usage events and in-memory aggregation.

Dayboard owns:

- associating usage with tenant, user, Run, provider, and configured model;
- durable PostgreSQL usage records;
- database-level exactly-once guarantees per Run;
- admission budgets, plan limits, pricing, and actual-versus-estimated reconciliation;
- deciding which usage metadata is safe to expose in product observability.

Basic token accounting is not agent middleware. A callback observes execution without
changing agent state or control flow. Middleware is introduced only when a policy must
participate in execution, such as warning an agent near a per-Run limit, preventing new
tool calls after a hard limit, or attributing subagent usage back to a parent step.

## Current Implementation

North emits normalized usage and `RuntimeUsageAccumulator` aggregates successful
`model.completed` callbacks by `call_id`. Dayboard consumes that accumulator and settles a
single `provider_usage_records` row from the Run's `finally` path using an independent database
session. Success, clarification, failure, interruption, and cancellation therefore share the
same settlement path whenever a model completion reported usage.

The database enforces uniqueness on `(tenant_id, run_id)`. Settlement inserts an immutable
aggregate and treats a conflict as an already-settled Run, so retries do not create a duplicate
or charge the budget again. A settlement failure is logged independently and does not replace
the Run's product outcome.

Dayboard also performs a conservative pre-call budget admission check. The first successful
settlement charges `max(actual_tokens - estimated_tokens, 0)` to the same fixed window. A lower
actual value is not refunded because a Run may settle after its admission window expires; a
negative adjustment could otherwise corrupt the next window. The PostgreSQL record remains the
authoritative actual usage fact.

## Required Follow-Up

Add an operational recovery path for the rare case where independent settlement exhausts its
database retry opportunity; the structured settlement failure log is the current detection
mechanism. If exact refunds become commercially necessary, replace fixed-window reservations
with a durable reservation model instead of applying negative counter adjustments.

Per-model buckets, cache-read tokens, lead/middleware/subagent attribution, running snapshots,
and token-budget middleware are deferred until the product uses multiple models, subagents,
or long-running executions that require active cost control.

## Consequences

The accounting source remains reusable across products without making North aware of tenants,
databases, prices, or plans. Dayboard can evolve billing independently while retaining the same
runtime usage facts.

Short scheduling commands avoid DeerFlow's full attribution and enforcement complexity. The
remaining tradeoff is that a database outage during settlement requires operational recovery;
the architecture treats that as accounting reliability work rather than a new middleware feature.
