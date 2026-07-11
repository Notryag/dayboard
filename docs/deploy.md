# Deploy

## GitHub

The repository can be public. Before pushing, verify that only placeholders are committed:

Current public repository:

```text
https://github.com/Notryag/dayboard
```

```bash
git status
git grep -n -I -E "(sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY=.+|api[_-]?key|password)"
```

Real secrets belong in `.env` or the deployment platform secret store. Do not commit `.env`.

## Vercel Web Deployment

Deploy only the Next.js app to Vercel.

Current Vercel deployment:

```text
https://web-red-rho-d3dz7i2rkr.vercel.app
```

The successful CLI deployment was run from `apps/web`. A repository import should set the root directory to `apps/web`; deploying from the repository root can fail Next.js detection unless the Vercel project is explicitly configured for the monorepo root.

Vercel project settings:

```text
Framework Preset: Next.js
Root Directory: apps/web
Install Command: npm install
Build Command: npm run build
Output Directory: .next
```

Required Vercel environment variable:

```text
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=https://your-api-host
```

For local development:

```text
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_DAYBOARD_BASE_PATH=
```

The server-hosted build uses:

```text
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=/dayboard-api
NEXT_PUBLIC_DAYBOARD_BASE_PATH=/dayboard
```

Password authentication uses an `HttpOnly`, `SameSite=Lax` server session cookie. Production web
and API endpoints must therefore be same-site, normally custom subdomains under one registrable
domain. Do not assume that a `vercel.app` web origin can use a session cookie issued by an unrelated
API domain. Keep `credentials: include` on HTTP requests and `withCredentials` on SSE connections.

## API Deployment

Do not deploy the FastAPI API to Vercel in the first version. Run it as a normal server service with Docker-managed PostgreSQL and Redis/Valkey.

Core API environment variables:

```text
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
DAYBOARD_RATE_LIMIT_STORAGE_URL=redis://...
DAYBOARD_CORS_ORIGINS=https://your-vercel-domain
APP_MODEL_NAME=openai:gpt-4o-mini
OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
OPENAI_API_KEY=...
```

The current server-hosted deployment uses password auth:

```text
DAYBOARD_AUTH_MODE=password
DAYBOARD_AUTH_COOKIE_SECURE=true
```

Keep provider credentials in the server environment or secret store only.

Current API deployment:

```text
https://www.selfapi.art/dayboard-api
```

Current server-hosted web deployment:

```text
https://www.selfapi.art/dayboard
```

Nginx proxies `/dayboard-api/` to the loopback-only FastAPI service on port 8000. The API and arq worker run as the enabled `dayboard-api.service` and `dayboard-worker.service` systemd units.

The account migration, web login release, and `DAYBOARD_AUTH_MODE=password` switch were deployed as
one batch. Preserve that coordination in future environments: deploying only the mode switch makes
an old web client return 401, while deploying only the login UI with development-mode business APIs
still uses the shared development identity.

The checked-in deployment templates are:

- `deploy/systemd/dayboard-web.service`
- `deploy/nginx/dayboard-locations.conf`

Build the server-hosted frontend with the server values above, enable the systemd unit, validate
Nginx with `nginx -t`, and reload it only after the web service is healthy on `127.0.0.1:3001`.

## Current Deployment Shape

```text
GitHub public repo
  -> server-hosted Next.js at /dayboard/ (primary China-access path)
  -> optional Vercel preview project rooted at apps/web
  -> HTTPS Nginx proxy on www.selfapi.art
  -> systemd FastAPI service and arq worker
  -> PostgreSQL and Redis/Valkey via Docker or managed services
```

The server Docker Compose deployment binds PostgreSQL and Redis to `127.0.0.1`. Do not expose either data service directly to the public network.
