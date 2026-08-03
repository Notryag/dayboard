# ADR-010 Use User Scope Until Shared Workspaces Exist

## Status

Accepted

## Context

Dayboard currently provides personal calendars, tasks, reminders, and Agent conversations. It has
users and sessions, but no workspace switcher, membership permissions, shared resources, or
organization boundary. The previous Tenant and TenantMembership tables therefore added schema and
authentication complexity without representing a real product capability.

## Decision

Use the authenticated user as the application isolation boundary:

- resolve an immutable `UserContext(user_id, timezone, locale)` at the HTTP boundary;
- pass `UserContext` explicitly through services and repositories;
- store `user_id` on user-owned business records and include it in user-local unique constraints;
- let Workers load `Run.user_id` from PostgreSQL before constructing `UserContext`;
- put only `run_id` in Redis jobs;
- defer a real `Workspace` and membership model until shared product workflows exist.

The pre-release schema is reset and the initial Alembic migration is regenerated. There is no
compatibility layer or dual representation of scope.

## Consequences

The active model is smaller and has one unambiguous scope. It does not claim to support multi-tenant
sharing. Repository filtering remains an application-level invariant; PostgreSQL row-level
security is not currently enabled.

When shared calendars or teams are introduced, add a first-class Workspace, membership, selected
workspace context, and authorization policy as one product change. Do not reintroduce a Tenant name
only to preserve an unused abstraction.
