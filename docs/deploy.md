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

These variables are compiled into the browser bundle by Next.js. They must be present when
`npm run build` runs. Setting them only on the later `next start` or systemd process does not
change an already-built bundle.

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

Build the server-hosted frontend with the server values above:

```bash
cd /path/to/dayboard/apps/web
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=/dayboard-api \
NEXT_PUBLIC_DAYBOARD_BASE_PATH=/dayboard \
npm run build
sudo systemctl restart dayboard-web.service
```

Do not run a plain `npm run build` for this subpath deployment. After restarting, verify the page,
one hashed static asset under `/dayboard/_next/static/`, and the API independently. A page `200`
alone is insufficient because the prerendered loading screen can render without a working browser
bundle or API URL.

```bash
curl -I https://your-host/dayboard
curl -I https://your-host/dayboard/_next/static/chunks/<chunk-from-page-source>.js
curl -I https://your-host/dayboard-api/api/auth/me
```

An unauthenticated `401` from `/api/auth/me` is a healthy response. Enable the systemd unit,
validate Nginx with `nginx -t`, and reload it only after the web service is healthy on
`127.0.0.1:3001`.

## Local Deployment

### Prerequisites And Layout

Install Docker with Compose, Node.js with npm, Python 3.11 or newer, and `uv`. The current API uses
the local editable `north` package, so keep both repositories as siblings unless the uv source path
is changed deliberately:

```text
workspace/
  dayboard/
  deerflow-lite/
```

Create local configuration from the tracked template. The default values are intended for the
Compose services bound to loopback:

```bash
cd /path/to/dayboard
cp .env.example .env
```

Add a real model gateway URL and key to `.env` before exercising Agent commands. Do not commit this
file. `DAYBOARD_AUTH_MODE=development` uses the fixed local identity. Set it to `password` to exercise
registration and login locally; keep `DAYBOARD_AUTH_COOKIE_SECURE=false` while serving over local
HTTP. Production password authentication requires HTTPS and `DAYBOARD_AUTH_COOKIE_SECURE=true`.

### PostgreSQL And Redis

Start the data services from the repository root:

```bash
docker compose up -d postgres redis
docker compose ps
```

Compose exposes both services only on the local machine. Processes running directly on the host use:

```text
DATABASE_URL=postgresql+asyncpg://dayboard:dayboard@localhost:5432/dayboard
REDIS_URL=redis://localhost:6379/0
DAYBOARD_COMMAND_QUEUE_URL=redis://localhost:6379/0
DAYBOARD_RATE_LIMIT_STORAGE_URL=redis://localhost:6379/1
DAYBOARD_PROVIDER_BUDGET_STORAGE_URL=redis://localhost:6379/2
```

The Redis database suffixes (`/0`, `/1`, `/2`) separate the command queue, rate limits, and provider
budgets logically while using the same Redis process. PostgreSQL persists product data in the
`dayboard_postgres_data` volume; Redis persists in `dayboard_redis_data`. Do not replace `localhost`
with the Compose service names unless the API and worker are also moved into the Compose network.

### Start The Application

Install API dependencies and apply migrations once, then keep the API and worker running in separate
terminals. Export the root `.env` because the commands run from `apps/api`:

```bash
cd /path/to/dayboard/apps/api
uv sync
set -a
source ../../.env
set +a
uv run alembic upgrade head
uv run fastapi dev src/dayboard/main.py
```

Worker terminal:

```bash
cd /path/to/dayboard/apps/api
set -a
source ../../.env
set +a
uv run arq dayboard.workers.commands.WorkerSettings
```

Web terminal:

```bash
cd /path/to/dayboard/apps/web
npm install
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=http://127.0.0.1:8000 \
NEXT_PUBLIC_DAYBOARD_BASE_PATH='' \
npm run dev
```

Open `http://localhost:3000`. The browser talks to FastAPI on port `8000`; FastAPI and the worker
talk to PostgreSQL on `5432` and Redis on `6379`. Keep `http://localhost:3000` in
`DAYBOARD_CORS_ORIGINS`. For a production-like local build, use the same two web variables with
`npm run build`, then `npm run start`.

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
