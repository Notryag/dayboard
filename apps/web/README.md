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
- `NEXT_PUBLIC_DAYBOARD_BASE_PATH`: Next.js mount path; empty for local and production deployments.

Both variables are compiled into the browser bundle. Production must set them while building the
Web image; changing only the environment of an existing container cannot update its browser assets.

## Production Deployment

Production does not run Next.js directly on the host. Build and start Web together with API,
Worker, PostgreSQL, and Redis through the root Docker Compose project. See the
[Docker deployment guide](../../docs/deploy.md).
