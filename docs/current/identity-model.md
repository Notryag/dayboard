# Identity And Data Scope

This is the implemented identity model after the pre-release tenant removal refactor.

## Decision

Dayboard is currently a multi-user personal scheduling application, not a workspace or
organization product. The authorization and persistence boundary is the authenticated user:

```text
UserContext(
  user_id,
  timezone,
  locale,
)
```

There is no `Tenant`, `TenantMembership`, `tenant_id`, or `owner_user_id` in the active schema or
application contracts. All user-owned business rows use `user_id`. Repositories require an
explicit `UserContext` and include `user_id` in every user-scoped read, write, lock, and delete.

This does not prevent a future shared product. If Dayboard adds shared calendars, teams, or
workspaces, introduce a real `Workspace` and membership model at that point. Do not preserve a
placeholder tenant abstraction whose selection and authorization semantics do not exist yet.

## Request And Worker Boundaries

HTTP authentication resolves a trusted `UserContext` through FastAPI dependency injection:

```text
session or Eval bearer identity
  -> UserRow + UserProfileRow
  -> UserContext
  -> service
  -> repository(user_id = context.user_id)
```

The request middleware only owns request IDs and structured logging cleanup. It does not infer
authorization from a caller-supplied header, and user scope is not hidden in a global ORM filter.

Workers keep a separate explicit recovery path:

```text
Redis job(run_id)
  -> system-scoped Run lookup
  -> persisted Run.user_id
  -> UserContext
  -> user-scoped service and repositories
```

Redis carries only `run_id`; it is not an identity authority. The Worker must never reconstruct
ownership from queue metadata or model arguments.

## Database Rules

- `users`, credentials, profiles, sessions, and external identities are global account records.
- Conversations, Runs, idempotency keys, schedules, reminders, voice transcripts, and provider
  usage records carry `user_id` when they are user-owned.
- Child records that are naturally scoped by a globally unique Run ID may rely on `run_id` for
  lookup, but their parent Run remains user-scoped.
- Unique constraints include `user_id` whenever the uniqueness rule is user-local, for example
  `(user_id, key)` for idempotency and `(user_id, run_id)` for provider usage.
- A missing user predicate is a storage defect. Application services must not query first and
  authorize later.

## Refactor Plan And Status

The pre-release reset was intentionally direct; no compatibility columns, dual writes, backfill,
feature flag, or legacy adapter is retained.

1. Remove Tenant and Membership domain rows, auth joins, settings, and `TenantIsolationMode`.
2. Replace `TenantContext` with immutable `UserContext` and rename `owner_user_id` to `user_id`.
3. Update Platform contracts, application services, repositories, tools, API routes, and Worker
   recovery to pass explicit user scope.
4. Replace the old Alembic baseline with `966685d63c93_initial_user_scoped_schema.py`.
5. Reset the development `dayboard` database and apply the new baseline.
6. Run package tests, API tests, migration checks, and residual-term checks before restarting
   local services.

All six items are implemented and verified in this working tree.
