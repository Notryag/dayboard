# Dayboard Documentation

## Start Here

Read only what the task needs:

1. [PROJECT_STATE.md](./PROJECT_STATE.md) for version, completed work, next milestone, known issues,
   and release checks.
2. [current/README.md](./current/README.md) for implemented product facts.
3. one task-specific guide below.

## Canonical Current Facts

- [current/architecture.md](./current/architecture.md): system and ownership boundaries.
- [current/product-model.md](./current/product-model.md): schedule/task semantics and product scope.
- [current/run-lifecycle.md](./current/run-lifecycle.md): Run states, Redis Streams, SSE, and recovery.

These are the only documents that should describe the whole current system. Update them with the
implementation that changes them.

## Engineering Guides

- [engineering-guidelines.md](./engineering-guidelines.md): coding, layering, testing, and safety.
- [ui-design.md](./ui-design.md): current visual and interaction rules.
- [tool-design.md](./tool-design.md): model-visible tools and dynamic binding.
- [api-errors.md](./api-errors.md): HTTP error envelope.
- [deploy.md](./deploy.md): production build, deployment, rollback, and health checks.
- [postgres-backup.md](./postgres-backup.md): backup and restore operations.

## Acceptance And Diagnostics

- [agent-acceptance.md](./agent-acceptance.md): targeted live-model acceptance program.
- [agent-eval.md](./agent-eval.md): 128-case quantitative Chinese scheduling benchmark.
- [token-usage-diagnostics.md](./token-usage-diagnostics.md): provider usage and cache diagnosis.
- [agent-token-optimization-history.md](./agent-token-optimization-history.md): append-only token
  optimization measurements.
- [TODO.md](./TODO.md): active token-efficiency and Northgate budget work.

## Decisions And History

- [adr/README.md](./adr/README.md): architectural decisions and rationale.
- [archive/README.md](./archive/README.md): expired phase plans; never use them as current guidance.

## Task Routing

Backend or database changes:

- current architecture and product model;
- engineering guidelines;
- API errors or backup runbook when relevant.

Agent, tool, or Run changes:

- current run lifecycle and product model;
- tool design;
- relevant ADRs;
- acceptance and token diagnostics when applicable.

Frontend changes:

- current architecture and product model;
- UI design;
- engineering guidelines.

Deployment changes:

- deploy runbook;
- PostgreSQL backup runbook before storage operations;
- PROJECT_STATE release checklist.
