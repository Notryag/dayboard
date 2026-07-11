# ADR-005 Authenticated Identity Boundary

## Status

Accepted

## Context

Dayboard carries `TenantContext` through all product services and repositories, but the current
FastAPI dependency always returns one configured development tenant and user. This is useful for
the Phase 1 prototype and unsafe for external users: every browser shares the same identity.

The first authentication provider has not been selected. The product should prefer services
that operate reliably for its China-based target users while retaining a standard boundary that
can support another provider or self-hosted identity later.

## Decision

Introduce a provider-neutral identity boundary before external beta access.

The API authentication adapter verifies a credential and returns trusted claims containing:

```text
issuer
subject
email or phone when verified and available
display name when available
```

Dayboard then resolves those claims through its own user and tenant-membership records. Only
that resolver constructs `TenantContext`:

```text
verified external identity
  -> Dayboard user
  -> active tenant membership
  -> user timezone and locale
  -> TenantContext
```

Provider tokens, organization claims, request headers, and model output never directly provide
Dayboard `tenant_id`, `user_id`, timezone, roles, or permissions.

Authentication adapters may support OIDC/JWT, a China-hosted managed identity service, or a
self-hosted provider. Provider SDK types remain inside `dayboard.integrations.identity`.
Repositories, scheduling tools, North, and domain schemas depend only on trusted Dayboard IDs
and `TenantContext`.

Two explicit runtime modes are allowed:

- `development`: one configured identity for local development and controlled demos;
- `authenticated`: verified credentials plus Dayboard user/membership resolution.

A production environment must refuse to start in `development` mode once authenticated mode is
introduced and configured for beta. The migration must be coordinated with a web login flow so
the existing client is not silently broken.

## Authorization Rules

- Authentication proves the external identity; Dayboard membership determines tenant access.
- Every product query continues to include tenant and owner scope.
- Thread and Run streaming require the same ownership checks as normal reads.
- An external subject is unique within its issuer, not globally by subject string alone.
- User timezone and locale come from the Dayboard profile, not untrusted request claims.
- Service-to-service and scheduled executions use separately authenticated internal identities,
  not a user-supplied header bypass.
- Development identity headers must never become a production authentication mechanism.

## Consequences

Dayboard can choose a provider without coupling business code to it, and changing providers does
not rewrite scheduling services. The product must add user, external identity, tenant membership,
and profile persistence before enabling authenticated mode.

Authentication cannot be completed as a backend-only toggle: the web client needs login,
session refresh, logout, and authenticated API/SSE requests in the same release milestone.
