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

North currently emits normalized usage and `RuntimeUsageAccumulator` aggregates successful
`model.completed` callbacks by `call_id`. Dayboard consumes that accumulator and writes a
`provider_usage_records` row for a successfully returned invocation.

Dayboard also performs a conservative pre-call budget admission check. This estimate protects
provider spend but is not the authoritative actual usage record.

## Required Follow-Up

Move Dayboard usage settlement into a Run finalization path that executes for success,
clarification, failure, interruption, and cancellation. Add a database uniqueness constraint
for one aggregate usage record per tenant and Run, and make retries return or update that
record instead of inserting duplicates.

Usage persistence failure must not overwrite the original Run outcome. It must be logged as
an operational accounting failure and remain recoverable. Actual usage can then reconcile
the conservative admission counters.

Per-model buckets, cache-read tokens, lead/middleware/subagent attribution, running snapshots,
and token-budget middleware are deferred until the product uses multiple models, subagents,
or long-running executions that require active cost control.

## Consequences

The accounting source remains reusable across products without making North aware of tenants,
databases, prices, or plans. Dayboard can evolve billing independently while retaining the same
runtime usage facts.

Short scheduling commands avoid DeerFlow's full attribution and enforcement complexity. The
tradeoff is that failed and cancelled usage remains incomplete until the finalization follow-up
is implemented; the architecture explicitly treats that as reliability work rather than a new
middleware feature.
