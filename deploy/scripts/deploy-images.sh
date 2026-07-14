#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="${DAYBOARD_PROJECT_DIR:-/home/zx/dayboard}"
IMAGE_TAG="${1:-}"
BACKUP_DIR="${DAYBOARD_BACKUP_DIR:-/var/backups/dayboard/postgres}"

if [[ ! "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]; then
  printf 'Usage: %s COMMIT_SHA\n' "$(basename "$0")" >&2
  exit 2
fi

cd "$PROJECT_DIR"

if [[ "$(git rev-parse HEAD)" != "$IMAGE_TAG" ]]; then
  printf 'Checked-out commit does not match image tag %s\n' "$IMAGE_TAG" >&2
  exit 1
fi

exec 9>"/tmp/dayboard-deploy.lock"
if ! flock -n 9; then
  printf 'Another Dayboard deployment is already running\n' >&2
  exit 1
fi

export DAYBOARD_IMAGE_TAG="$IMAGE_TAG"
compose=(docker compose -f docker-compose.yml -f docker-compose.deploy.yml)

"${compose[@]}" config --quiet
"${compose[@]}" pull api worker web

sudo -n env \
  DAYBOARD_PROJECT_DIR="$PROJECT_DIR" \
  DAYBOARD_BACKUP_DIR="$BACKUP_DIR" \
  "$PROJECT_DIR/deploy/scripts/postgres-backup.sh"

"${compose[@]}" run --rm --no-deps api /app/.venv/bin/alembic upgrade head
"${compose[@]}" up -d --no-build api worker web

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:8000/health >/dev/null
curl -fsS http://127.0.0.1:3001/dayboard/ >/dev/null
"${compose[@]}" ps api worker web

printf '%s\n' "$IMAGE_TAG" > .dayboard-deployed-image.tmp
mv .dayboard-deployed-image.tmp .dayboard-deployed-image
printf 'Deployed Dayboard image tag %s\n' "$IMAGE_TAG"
