# Backend Simplification Audit

> Time-bounded audit for the pre-release abstraction freeze. This file records concrete call paths
> at the start of the cleanup and is not a canonical architecture document. Move it to
> `docs/archive/` when the listed decisions are complete. Current contracts remain under
> `docs/current/`.

## Scope And Guardrails

This audit looks for parameter-only forwarding in three production paths. It does not authorize
changes to transaction ownership, durable state, concurrency control, authorization, event order,
or public protocols.

The following invariants are out of scope for simplification:

- Redis command jobs carry only `run_id`; the Worker restores trusted state from PostgreSQL.
- PostgreSQL is authoritative for Runs, messages, Interactions, schedules, reminders, and usage.
- `queued -> running` commits before North or a model provider is called.
- No database transaction remains open while North or ASR performs external work.
- terminal Run state, assistant message, presentation, and optional Interaction commit atomically.
- terminal PostgreSQL state is committed before the terminal browser event and stream end marker.
- clarification uses database compare-and-consume state versions.
- schedule writes use `expected_row_version` and replace Reminder state in the same transaction.
- trusted `UserContext`, Run identity, and operation keys are injected by server code.
- application and Platform contracts never expose SQLAlchemy rows.

## Path 1: Submit A Command

```text
POST /api/command-runs
  -> dayboard.api.routes.create_command_run
  -> FastAPI get_command_service dependency
  -> dayboard.composition.commands.build_command_service
  -> dayboard.app.commands.CommandService.create_or_get_command_run
  -> agent_platform.application.CommandSubmissionService.submit
  -> IdempotencyService + ConversationService + AgentRunService
  -> SqlAlchemyPlatformUnitOfWork stores
  -> one commit
  -> RedisCommandDispatcher.enqueue(run_id)
  -> HTTP 202
```

| Step | File and callable | Decision or invariant | IO | Pure forwarding |
| --- | --- | --- | --- | --- |
| HTTP boundary | `dayboard/api/routes.py:create_command_run` | maps idempotency and active-Run conflicts; enqueues only newly created Runs; persists queue failure | Redis through dispatcher | no |
| FastAPI dependency | `dayboard/api/dependencies.py:get_command_service` | request-scoped Session wiring | none | construction boundary |
| command composition | `dayboard/composition/commands.py:build_command_service` | selects Dayboard failure projection and clarification adapter | none | mostly construction |
| nested composition helper | `dayboard/composition/commands.py:build_command_service_from_platform` | none beyond the same construction | none | candidate |
| product command service | `dayboard/app/commands.py:CommandService.create_or_get_command_run` | request identity, Thread title, product logging | through Platform | no |
| clarification continuation | `dayboard/app/commands.py:CommandService.create_or_get_clarification_run` | validates the selected option before atomic consume and resubmission | through Platform | no |
| generic submission | `agent_platform/application/command_submission_service.py:submit` | idempotency claim, active Thread, Interaction CAS, Run/event/message atomic group | repository ports | no |
| Run creation | `agent_platform/application/run_service.py:create_run` | creates `queued` Run and `run_created` event together | repository ports | no |
| persistence adapter | `dayboard/db/platform_uow.py:SqlAlchemyPlatformUnitOfWork` | binds all Platform stores to one transaction | PostgreSQL | no |

Initial decisions:

- Keep the FastAPI dependency: it is the transport-to-composition boundary.
- Keep `CommandService`: it contains Dayboard policy and clarification continuation behavior.
- Keep `CommandSubmissionService`: it owns the atomic submission use case.
- Inline or remove `build_command_service_from_platform` if no independent caller needs it.
- Review the `create_command_run` convenience method separately; production uses the richer result,
  while tests currently use the UUID-only wrapper.

## Path 2: Execute A Run

```text
arq execute_command_run(run_id)
  -> open request-independent AsyncSession
  -> build_run_execution_scope
  -> restore Run and trusted UserContext from PostgreSQL
  -> RunExecutionCoordinator.execute
  -> commit queued -> running and run_started
  -> DayboardRunExecutionDriver.execute
  -> North RunExecutor
  -> scheduling tools and runtime event projection
  -> RunExecutionCoordinator complete/fail callback
  -> commit terminal Run + assistant message + presentation/Interaction
  -> publish terminal Redis event
```

| Step | File and callable | Decision or invariant | IO | Pure forwarding |
| --- | --- | --- | --- | --- |
| arq boundary | `dayboard/workers/commands.py:execute_command_run` | restores owner identity from Run; queue input remains `run_id` only | PostgreSQL | no |
| Run composition | `dayboard/composition/runs.py:build_run_execution_scope` | assembles one driver, lock, budget guard, usage settlement, runtime-event UoW factory, North factory, and stream bridge | none | no |
| scope method | `dayboard/composition/runs.py:RunExecutionScope.execute` | none; forwards coordinator, context, Run, and driver | none | candidate |
| lifecycle coordinator | `agent_platform/application/run_execution_coordinator.py:execute` | state machine, pre-provider commit, one terminal settlement, atomic outcome persistence | PostgreSQL through UoW | no |
| product driver | `dayboard/agent/run_execution.py:DayboardRunExecutionDriver.execute` | budget, North invocation, durable progress, presentation projection, usage, terminal publication order | North, PostgreSQL, Redis, provider | no |
| runtime | North `RunExecutor` | model/tool execution, compaction, canonical runtime events | provider and tools | no |

Initial decisions:

- Do not simplify this path in the command-submission cleanup.
- `RunExecutionScope.execute` is a proven one-line forwarding candidate, but removing it is a separate
  low-risk change after worker tests confirm the direct call remains readable.
- Preserve `RunExecutionCoordinator`, the driver, per-event fresh UoW, and terminal callback order.

## Path 3: Reschedule A Calendar Entry

```text
North tool call
  -> dayboard.agent.tools.agent_reschedule_calendar_entry
  -> parse Beijing local model values into trusted timezone-aware datetimes
  -> dayboard.tools.scheduling.reschedule_calendar_entry
  -> operation idempotency + target/CAS validation + duration/conflict policy
  -> SchedulingService.reschedule_calendar_entry
  -> CalendarEntryRepository.reschedule(expected_row_version)
  -> SchedulingService._sync_calendar_reminder
  -> construct compact receipt + complete presentation artifact
  -> serialized tool boundary commit
```

The direct HTTP edit path joins at `SchedulingService.update_calendar_entry_from_ui`, then commits at
the API boundary.

| Step | File and callable | Decision or invariant | IO | Pure forwarding |
| --- | --- | --- | --- | --- |
| model boundary | `dayboard/agent/tools.py:agent_reschedule_calendar_entry` | model schema validation, Beijing-local conversion, trusted Run operation key, receipt/artifact split | none | no |
| serialized tool use case | `dayboard/tools/scheduling.py:reschedule_calendar_entry` | idempotent replay, target validation, duration semantics, conflict reporting, optimistic-lock failure | through application service | no |
| scheduling service | `dayboard/app/scheduling.py:SchedulingService.reschedule_calendar_entry` | schedule mutation and Reminder synchronization remain one use case | repository ports | no |
| scheduling UoW | `dayboard/db/scheduling_uow.py:SqlAlchemySchedulingUnitOfWork` | binds Calendar, Task, and Reminder stores to one transaction | PostgreSQL | no |
| repository | `dayboard/db/repositories.py:CalendarEntryRepository.reschedule` | user scope and `row_version` CAS in one SQL update | PostgreSQL | no |
| commit owner | `dayboard/agent/tools.py:serialize_tool` | commits only after receipt and artifact construction; rolls back any failure | PostgreSQL | no |

Initial decision: do not remove a layer from this path. Its length reflects distinct protocol,
business-policy, transaction, persistence, and presentation responsibilities rather than repeated
parameter forwarding.

## Composition Audit Queue

Review scopes by lifecycle instead of enforcing a numerical scope limit:

| Scope | Why callers need the wrapper | Initial action |
| --- | --- | --- |
| `PlatformServiceScope` | several services share one Platform transaction | keep |
| `RunExecutionScope` | groups Platform state lookup with one Run driver | review only the forwarding method |
| `SchedulingServiceScope` | API/tool callers need the service/query plus explicit commit boundary | keep |
| `ReminderServiceScope` | API/Worker callers explicitly commit the reminder transaction | keep |
| `AccountRecoveryServiceScope` | API commits credential/token/session atomic groups | keep |
| `VoiceServiceScope` | callers only use `transcriptions`; the service itself controls its multi-phase transactions | simplification candidate |

Do not add an `AppContainer` during this cleanup. The current explicit Session-based builders are
small and searchable; a process container would be justified only by demonstrated lifetime or
construction problems.

## Interface Audit Rule

Implementation count alone is not sufficient evidence for deleting a Protocol. Keep storage,
provider, execution, clock, and deterministic-test boundaries even with one production adapter.
Delete an interface only when it has one implementation, one caller, no useful fake, and does not
protect application code from infrastructure or an external protocol.

## Completion Criteria

- following command submission no longer crosses a redundant nested composition helper;
- each retained scope has an explicit transaction or lifecycle reason in this audit;
- no public API, database schema, event order, or transaction boundary changes;
- targeted command and worker checks pass;
- this audit moves to `docs/archive/` after the decisions are complete;
- the next three meaningful changes prioritize product behavior or experience, not architecture.
