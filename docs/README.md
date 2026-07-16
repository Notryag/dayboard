# Dayboard Docs

Use this page as the documentation entry point. Do not load every document at once unless you need the full context.

## Start Here

For a new session, read only:

1. [../README.md](../README.md)
2. [PROJECT_STATE.md](./PROJECT_STATE.md)
3. the task-specific section below

## Task-Based Reading

Backend implementation:

- [architecture.md](./architecture.md)
- [api-errors.md](./api-errors.md) for the HTTP error response contract
- [engineering-guidelines.md](./engineering-guidelines.md)
- [phase-2-plan.md](./phase-2-plan.md) for current milestone work
- [phase-1-plan.md](./phase-1-plan.md) for the completed foundation plan

Authentication and account ownership:

- [adr/005-authenticated-identity-boundary.md](./adr/005-authenticated-identity-boundary.md)
- [architecture.md](./architecture.md), sections "Tenant Extensibility" and "API Surface"
- [engineering-guidelines.md](./engineering-guidelines.md), sections "Tenant Context", "Database Rules", and "API Rules"
- [phase-2-plan.md](./phase-2-plan.md), section "P2.1 Real Identity And Ownership"

Reminder delivery:

- [architecture.md](./architecture.md), section "Reminder Delivery"
- [phase-2-plan.md](./phase-2-plan.md), section "P2.2 Reminder Delivery"
- [engineering-guidelines.md](./engineering-guidelines.md), sections "Database Rules" and "Backend Layers"

Agent and tools:

- [architecture.md](./architecture.md), sections "System Overview", "Intent Recognition And Tool Selection",
  "Command Execution Sequence", "Agent Assembly Boundary", and "Product Tools"
- [engineering-guidelines.md](./engineering-guidelines.md), sections "Tool Design" and "Agent And LLM Rules"
- [product-and-scope.md](./product-and-scope.md), section "Minimum Data Contract"
- [agent-acceptance.md](./agent-acceptance.md) for explicit live model acceptance runs

Frontend:

- [architecture.md](./architecture.md), sections "Technology Choices", "Project Shape", and "API Surface"
- [engineering-guidelines.md](./engineering-guidelines.md), section "Frontend Rules"
- [ui-design.md](./ui-design.md)

Database:

- [architecture.md](./architecture.md), sections "Database Model", "Tenant Extensibility", and "Concurrency And Reliability"
- [engineering-guidelines.md](./engineering-guidelines.md), section "Database Rules"
- [postgres-backup.md](./postgres-backup.md) for production backup, restore rehearsal, and recovery

Product scope:

- [product-and-scope.md](./product-and-scope.md)

Current milestone planning:

- [phase-2-plan.md](./phase-2-plan.md)
- [phase-1-plan.md](./phase-1-plan.md) as completed historical context

Architecture decisions:

- [adr/README.md](./adr/README.md)

Deployment:

- [deploy.md](./deploy.md) for the Docker Compose production runbook
- [postgres-backup.md](./postgres-backup.md) before changing production PostgreSQL data or volumes

## Loading Guidance

- Start with [PROJECT_STATE.md](./PROJECT_STATE.md) to understand the current direction.
- Read [architecture.md](./architecture.md) when changing backend, agent, storage, API, or infrastructure boundaries.
- Read [engineering-guidelines.md](./engineering-guidelines.md) before adding code.
- Read [ui-design.md](./ui-design.md) before changing the main chat UI, theme variables, or component system.
- Read [deploy.md](./deploy.md) before changing Docker Compose, Nginx, production services, or
  deployment secrets.
- Read ADRs only when making or revisiting a major technical decision.
- Avoid pulling all docs into context for small edits.
