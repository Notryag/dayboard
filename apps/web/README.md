# Dayboard Web

The Dayboard web app is a Next.js client for the FastAPI command, account, and Run SSE APIs.

## Local Development

Start the API and worker first, then run:

```bash
npm install
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=http://127.0.0.1:8000 \
NEXT_PUBLIC_DAYBOARD_BASE_PATH='' \
npm run dev
```

Open `http://localhost:3000`. Local API CORS configuration must include this origin.

## Environment Variables

- `NEXT_PUBLIC_DAYBOARD_API_BASE_URL`: browser-visible FastAPI base URL or same-site path.
- `NEXT_PUBLIC_DAYBOARD_BASE_PATH`: Next.js mount path; empty locally and `/dayboard` on the
  server-hosted deployment.

Both variables are compiled into the browser bundle. Set them when running `npm run build`; setting
them only for `npm run start` cannot change an existing build.

## Server Build

```bash
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=/dayboard-api \
NEXT_PUBLIC_DAYBOARD_BASE_PATH=/dayboard \
npm run build
npm run start -- --hostname 127.0.0.1 --port 3001
```

See [../../docs/deploy.md](../../docs/deploy.md) for the full API, worker, database, reverse proxy,
and verification procedure.
