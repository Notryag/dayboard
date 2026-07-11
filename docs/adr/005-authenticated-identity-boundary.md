# ADR-005 Authenticated Identity Boundary

## Status

Accepted

## Context

Dayboard carries `TenantContext` through all product services and repositories, but the current
FastAPI dependency always returns one configured development tenant and user. This is useful for
the Phase 1 prototype and unsafe for external users: every browser shares the same identity.

The first beta only needs reliable registration and login. Adding a separate Node authentication
service or depending on an overseas identity control plane would add deployment and China-network
risk before the product needs social login.

## Decision

Implement the first identity flow inside the FastAPI service:

- username and optional email registration;
- Argon2id password hashes;
- opaque, revocable server-side sessions;
- an `HttpOnly` session cookie whose raw token is never stored in PostgreSQL;
- Dayboard-owned users, profiles, tenants, and memberships.

Store only a SHA-256 digest of each random session token. Logout revokes the server-side session.
Password hashes, raw passwords, raw session tokens, and cookie values must never be logged.

Keep a provider-neutral external identity table for later WeChat, OIDC, or another China-hosted
provider. External providers are adapters into the same Dayboard user and membership resolver;
they do not replace Dayboard ownership records.

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
verified password session or external identity
  -> Dayboard user
  -> active tenant membership
  -> user timezone and locale
  -> TenantContext
```

Provider tokens, organization claims, request headers, and model output never directly provide
Dayboard `tenant_id`, `user_id`, timezone, roles, or permissions.

Future authentication adapters may support WeChat, OIDC/JWT, or a China-hosted managed identity
service. Provider SDK types remain inside `dayboard.integrations.identity`.
Repositories, scheduling tools, North, and domain schemas depend only on trusted Dayboard IDs
and `TenantContext`.

Two explicit runtime modes are allowed:

- `development`: one configured identity for local development and controlled demos;
- `password`: verified server-side session plus Dayboard user/membership resolution.

A production environment must refuse to start in `development` mode once authenticated mode is
introduced and configured for beta. The migration must be coordinated with a web login flow so
the existing client is not silently broken.

## Authorization Rules

- Authentication proves the account identity; Dayboard membership determines tenant access.
- Every product query continues to include tenant and owner scope.
- Thread and Run streaming require the same ownership checks as normal reads.
- Usernames and normalized emails are unique for password login.
- An external subject is unique within its issuer, not globally by subject string alone.
- User timezone and locale come from the Dayboard profile, not untrusted request claims.
- Service-to-service and scheduled executions use separately authenticated internal identities,
  not a user-supplied header bypass.
- Development identity headers must never become a production authentication mechanism.

## Consequences

Dayboard can ship a China-network-independent first login without coupling business code to a
provider. Adding WeChat later links an external identity to the same user instead of rewriting
scheduling services.

Authentication cannot be completed as a backend-only toggle: the web client needs login,
session refresh, logout, and authenticated API/SSE requests in the same release milestone.
