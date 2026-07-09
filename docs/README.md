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
- [engineering-guidelines.md](./engineering-guidelines.md)
- [phase-1-plan.md](./phase-1-plan.md)

Agent and tools:

- [architecture.md](./architecture.md), sections "Agent Assembly Boundary", "Product Tools", and "Create Calendar Entry Flow"
- [engineering-guidelines.md](./engineering-guidelines.md), sections "Tool Design" and "Agent And LLM Rules"
- [product-and-scope.md](./product-and-scope.md), section "Minimum Data Contract"

Frontend:

- [architecture.md](./architecture.md), sections "Technology Choices", "Project Shape", and "API Surface"
- [engineering-guidelines.md](./engineering-guidelines.md), section "Frontend Rules"
- [ui-design.md](./ui-design.md)

Database:

- [architecture.md](./architecture.md), sections "Database Model", "Tenant Extensibility", and "Concurrency And Reliability"
- [engineering-guidelines.md](./engineering-guidelines.md), section "Database Rules"

Product scope:

- [product-and-scope.md](./product-and-scope.md)

Current milestone planning:

- [phase-1-plan.md](./phase-1-plan.md)

Architecture decisions:

- [adr/README.md](./adr/README.md)

Deployment:

- [deploy.md](./deploy.md)

## Loading Guidance

- Start with [PROJECT_STATE.md](./PROJECT_STATE.md) to understand the current direction.
- Read [architecture.md](./architecture.md) when changing backend, agent, storage, API, or infrastructure boundaries.
- Read [engineering-guidelines.md](./engineering-guidelines.md) before adding code.
- Read [ui-design.md](./ui-design.md) before changing the main chat UI, theme variables, or component system.
- Read [deploy.md](./deploy.md) before changing GitHub, Vercel, API hosting, or secret handling.
- Read ADRs only when making or revisiting a major technical decision.
- Avoid pulling all docs into context for small edits.
