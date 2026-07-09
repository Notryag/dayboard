# Deploy

## GitHub

The repository can be public. Before pushing, verify that only placeholders are committed:

```bash
git status
git grep -n -I -E "(sk-[A-Za-z0-9_-]{20,}|OPENAI_API_KEY=.+|api[_-]?key|password)"
```

Real secrets belong in `.env` or the deployment platform secret store. Do not commit `.env`.

## Vercel Web Deployment

Deploy only the Next.js app to Vercel.

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
```

## API Deployment

Do not deploy the FastAPI API to Vercel in the first version. Run it as a normal server service with Docker-managed PostgreSQL and Redis/Valkey.

Required API environment variables:

```text
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
DAYBOARD_RATE_LIMIT_STORAGE_URL=redis://...
DAYBOARD_CORS_ORIGINS=https://your-vercel-domain
APP_MODEL_NAME=openai:gpt-4o-mini
OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
OPENAI_API_KEY=...
```

Keep provider credentials in the server environment or secret store only.

## Current Deployment Shape

```text
GitHub public repo
  -> Vercel project rooted at apps/web
  -> API server runs apps/api
  -> PostgreSQL and Redis/Valkey via Docker or managed services
```
