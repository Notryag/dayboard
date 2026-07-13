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
`npm run build` runs. Setting them only at container runtime does not change an already-built
bundle.

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
DAYBOARD_RATE_LIMIT_REGISTRATION=5/hour
DAYBOARD_RATE_LIMIT_LOGIN=10/minute
DAYBOARD_RATE_LIMIT_COMMAND=20/minute
DAYBOARD_RATE_LIMIT_VOICE=10/minute
DAYBOARD_ASR_PROVIDER=aliyun
DAYBOARD_ASR_MAX_AUDIO_SECONDS=60
DAYBOARD_ASR_MAX_UPLOAD_BYTES=10485760
ALIYUN_ASR_API_KEY=...
ALIYUN_ASR_MODEL=qwen3-asr-flash
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

The microphone stays disabled when the configured ASR provider has no credential. After adding or
rotating `ALIYUN_ASR_API_KEY`, rebuild and recreate API and Web, then verify
`GET /api/voice/capabilities` reports `available: true`. The API runs PyAV media inspection in an
isolated, time-limited subprocess to enforce decoded audio duration before a provider call. Uploaded
audio is held only for request processing; Dayboard persists transcript text and metadata, not raw
audio bytes.

Current API deployment:

```text
https://www.selfapi.art/dayboard-api
```

Current server-hosted web deployment:

```text
https://www.selfapi.art/dayboard
```

## Production Handoff

The active checkout and Compose project are:

```text
/home/zx/dayboard
```

Do not operate production from `/root/dayboard`. That path belongs to the previous systemd-based
deployment. The installed `dayboard-api.service`, `dayboard-worker.service`, and
`dayboard-web.service` units are disabled and inactive; do not re-enable them while Compose owns the
application ports.

Production ownership is:

```text
Nginx
  -> 127.0.0.1:8000 -> Compose API
  -> 127.0.0.1:3001 -> Compose Web
Compose
  -> API, Worker, Web, PostgreSQL, Redis
```

Start every production session by checking repository and runtime state:

```bash
cd /home/zx/dayboard
git status --short --branch
docker compose config --quiet
docker compose ps
systemctl is-enabled dayboard-api.service dayboard-worker.service dayboard-web.service
systemctl is-active dayboard-api.service dayboard-worker.service dayboard-web.service
```

Expected service-manager state is `disabled` and `inactive` for all three old systemd units.
Expected Compose state is running PostgreSQL, Redis, API, Worker, and Web containers; PostgreSQL,
Redis, API, and Worker should report `healthy`.

For an application deployment, build before recreating containers:

```bash
cd /home/zx/dayboard
docker compose build api worker web
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3001/dayboard
```

The API health response must report `database`, `redis`, and `worker` as `ok`; the Web check must
return HTTP 200. Inspect failures with:

```bash
docker compose logs --tail=100 api worker web
```

Compose uses restart policies for host reboots. Do not add a second process manager for the
application containers. Never run `docker compose down -v`, remove the named volumes, or replace
`.env` without confirming a backup and recovery plan. Real secrets stay only in `.env` or a secret
store and must not be copied into images or committed.

PostgreSQL backups are created by a systemd timer that invokes the Compose-aware backup script. The
timer is only an operational scheduler; Docker Compose remains the application process manager.
Install it and create the first verified backup before any destructive database operation:

```bash
cd /home/zx/dayboard
sudo install -d -m 0700 /var/backups/dayboard/postgres
sudo install -m 0644 deploy/systemd/dayboard-postgres-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/dayboard-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dayboard-postgres-backup.timer
sudo systemctl start dayboard-postgres-backup.service
sudo deploy/scripts/postgres-restore-rehearsal.sh
```

The complete installation, verification, restore, rollback, and troubleshooting runbook is in
[postgres-backup.md](./postgres-backup.md). The restore script intentionally refuses to overwrite
the active database and restores into a new database for an explicit application cutover.

Nginx proxies `/dayboard-api/` to the loopback-only FastAPI container on port 8000. The API, Web, Worker, PostgreSQL, and Redis services run from the root `docker-compose.yml` file. The application containers bind only to loopback ports; Nginx remains the public entry point.

The account migration, web login release, and `DAYBOARD_AUTH_MODE=password` switch were deployed as
one batch. Preserve that coordination in future environments: deploying only the mode switch makes
an old web client return 401, while deploying only the login UI with development-mode business APIs
still uses the shared development identity.

The checked-in deployment templates are:

- `deploy/github-actions/ci.yml` (copy to `.github/workflows/ci.yml` using GitHub credentials with
  workflow-write permission to enable it)
- `docker-compose.yml` and the application Dockerfiles
- `deploy/nginx/dayboard-locations.conf`
- `deploy/scripts/postgres-*.sh` and `deploy/systemd/dayboard-postgres-backup.*`

The Compose Web build injects `/dayboard-api` and `/dayboard` into the browser bundle. After a
deployment, verify the page, one hashed static asset under `/dayboard/_next/static/`, and the API
independently. A page `200` alone is insufficient because the prerendered loading screen can render
without a working browser bundle or API URL.

```bash
curl -I https://your-host/dayboard
curl -I https://your-host/dayboard/_next/static/chunks/<chunk-from-page-source>.js
curl -I https://your-host/dayboard-api/api/auth/me
```

An unauthenticated `401` from `/api/auth/me` is a healthy response. Validate Nginx with `nginx -t`,
and reload it only after the web container is healthy on
`127.0.0.1:3001`.

## Local Deployment

### Prerequisites And Layout

Install Docker with Compose, Node.js with npm, Python 3.11 or newer, and `uv`. Normal installs fetch
the pinned `north` commit from the `deerflow-lite` Git repository, so a clean Dayboard checkout is
self-contained. When changing Dayboard and north together, the repositories may be kept as siblings
and the pinned package can be temporarily replaced in the active virtual environment:

```text
workspace/
  dayboard/
  deerflow-lite/
```

```bash
cd /path/to/dayboard/apps/api
uv sync
uv pip install --editable /path/to/deerflow-lite/packages/harness
```

Do not commit a local path override. Before committing a Dayboard change that requires new north
behavior, push north first, update the pinned commit in `apps/api/pyproject.toml`, and regenerate
`apps/api/uv.lock`.

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
  -> Docker Compose FastAPI service and arq worker
  -> PostgreSQL and Redis/Valkey via Docker or managed services
```

The server Docker Compose deployment binds PostgreSQL and Redis to `127.0.0.1`. Do not expose either data service directly to the public network.
