# ADR-006 Tenant Isolation and External Tool Boundaries

## Status

Accepted

## Context

Dayboard stores multiple users and tenants in one PostgreSQL database. Scheduling, conversation,
Run, reminder, voice, and provider-usage records are product data and must never cross an
authenticated tenant or owner boundary.

North executes tools but does not own Dayboard identity or authorization. Future external tools,
including private knowledge search, may call services outside the Dayboard process. Allowing the
model or browser to provide identity fields to those tools would turn prompt output into an
authorization decision.

DeerFlow 2.0 provides useful owner-isolation patterns, especially fail-closed repository access,
trusted runtime identity, and user-scoped files. Dayboard keeps its explicit tenant model instead
of copying DeerFlow's user-only context, default-user fallback, Gateway, or authorization stack.

## Decision

Use application-enforced shared-database isolation:

- authentication and an active membership produce an immutable `TenantContext`;
- product services and repositories require that context explicitly;
- owner-scoped rows carry both `tenant_id` and `owner_user_id`;
- reads, writes, streams, cancellation, usage records, and background work apply the same scope;
- production has no unauthenticated default identity;
- dedicated schemas or databases remain future deployment options, not separate service APIs.

Agent and external tool schemas contain only model-controlled business inputs. The following are
trusted server context and must be injected after authentication:

```text
tenant_id, user_id, owner_user_id, timezone, locale,
run_id, thread_id, request_id, permissions
```

Dayboard validates this rule while assembling the Agent. A tool exposing one of these names to the
model is rejected before invocation.

External tools remain ordinary injected LangChain/North tools. For example, a future knowledge
search tool accepts `query`, `limit`, and business filters while its closure or service object owns
the authenticated `TenantContext`, database session, credentials, and authorization policy. North
does not add a product RAG abstraction or store Dayboard embeddings.

Redis jobs carry only `run_id`. Workers restore identity and input text from the persisted Dayboard
Run and its authenticated ownership records. Queue metadata and model arguments are not independent
authority. Tenant-scoped files and future document chunks use the same trusted tenant and owner
identifiers.

Tenant switching, shared calendars, and role permissions are deferred until one account can
actively operate in more than one tenant. At that point the selected tenant must be stored in a
trusted session or request credential and checked against an active membership. The existing
membership `role` field is not authorization by itself.

## Consequences

Adding a business or external tool requires an explicit server-side context binding. Cross-tenant
tests remain required for every new repository and externally reachable Run or file operation.

This approach does not provide PostgreSQL row-level security. A missing repository predicate is
still an application defect, so repository APIs must continue to require `TenantContext` and fail
closed. PostgreSQL RLS can be considered later as defense in depth if enterprise deployments need
database-enforced isolation.

Dayboard avoids importing a generic Principal/RBAC framework before the product has shared-tenant
workflows, while preserving a clear path to add one at the application boundary.
