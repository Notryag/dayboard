# ADR-003 Separate Conversation and Checkpoint Persistence

## Status

Accepted on 2026-07-10.

## Context

North accepts a LangGraph `thread_id`, but its original fallback created an in-memory saver for
each agent build. Dayboard also passed `run.id` as `thread_id`, so every command was isolated even
though `agent_runs` already records a distinct thread identifier.

DeerFlow separates thread metadata, LangGraph checkpoints, run journals, and thread-scoped files.
Its checkpointer supports memory, SQLite, and PostgreSQL; summarization compacts runtime messages
into `summary_text`, while run history preserves messages the product UI must continue to show.

## Decision

- Dayboard owns product conversations, tenant authorization, visible messages, retention,
  structured pending actions, and summaries exposed to users.
- North owns reusable checkpointer construction and runtime state continuity.
- `conversation_thread.id` is the runnable `thread_id`; `agent_run.id` identifies one execution.
- Checkpoints are runtime internals and are not Dayboard's chat-history API.
- Context compaction may remove messages from LangGraph state only after a host hook can archive
  them. It must never delete the product's visible message history.
- The worker owns the async checkpointer lifecycle and injects one shared saver into all agents.

## Rollout

1. Add North's configurable async checkpointer provider and use the real run `thread_id`.
2. Add Dayboard conversation/thread and message persistence plus thread-scoped run APIs.
3. Enable North's PostgreSQL saver in the worker.
4. Add configurable summarization and a pre-compaction archive hook.
5. Assemble model context from durable product state, summary, and recent complete turns.

The first rollout step keeps the worker on the memory backend until Dayboard exposes stable
product threads. This avoids accumulating permanent checkpoints that no client can resume yet.
