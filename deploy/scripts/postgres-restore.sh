#!/usr/bin/env bash

set -Eeuo pipefail

umask 077

usage() {
  printf 'Usage: %s BACKUP_FILE NEW_DATABASE_NAME\n' "$(basename "$0")" >&2
  printf 'The target must be a new database and cannot be the active production database.\n' >&2
}

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

backup_file="$1"
target_database="$2"

if [[ ! "$target_database" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  printf 'Database name must contain only letters, numbers, and underscores\n' >&2
  exit 2
fi

if [[ ! -r "$backup_file" || ! -s "$backup_file" ]]; then
  printf 'Backup is missing, unreadable, or empty: %s\n' "$backup_file" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${DAYBOARD_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
backup_file="$(cd "$(dirname "$backup_file")" && pwd)/$(basename "$backup_file")"
checksum_file="$backup_file.sha256"

command -v docker >/dev/null 2>&1 || {
  printf 'docker is required\n' >&2
  exit 1
}
command -v sha256sum >/dev/null 2>&1 || {
  printf 'sha256sum is required\n' >&2
  exit 1
}

if [[ -f "$checksum_file" ]]; then
  (
    cd "$(dirname "$checksum_file")"
    sha256sum --check --status "$(basename "$checksum_file")"
  ) || {
    printf 'Backup checksum verification failed: %s\n' "$backup_file" >&2
    exit 1
  }
else
  printf 'Backup checksum file is required: %s\n' "$checksum_file" >&2
  exit 1
fi

cd "$PROJECT_DIR"

production_database="$(docker compose exec -T postgres sh -ceu 'printf %s "$POSTGRES_DB"')"
postgres_user="$(docker compose exec -T postgres sh -ceu 'printf %s "$POSTGRES_USER"')"

if [[ "$target_database" == "$production_database" ]]; then
  printf 'Refusing to overwrite the active production database: %s\n' "$production_database" >&2
  exit 1
fi

database_exists="$(
  docker compose exec -T postgres psql \
    --username "$postgres_user" \
    --dbname "$production_database" \
    --tuples-only \
    --no-align \
    --command "SELECT 1 FROM pg_database WHERE datname = '$target_database'"
)"
if [[ "$database_exists" == "1" ]]; then
  printf 'Refusing to overwrite existing database: %s\n' "$target_database" >&2
  exit 1
fi

docker compose exec -T postgres pg_restore --list <"$backup_file" >/dev/null
docker compose exec -T postgres createdb \
  --username "$postgres_user" \
  "$target_database"

database_created=1
cleanup_failed_restore() {
  status=$?
  if [[ $status -ne 0 && ${database_created:-0} -eq 1 ]]; then
    printf 'Restore failed; removing incomplete database %s\n' "$target_database" >&2
    docker compose exec -T postgres dropdb \
      --username "$postgres_user" \
      --if-exists \
      --force \
      "$target_database" >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup_failed_restore EXIT

docker compose exec -T postgres pg_restore \
  --username "$postgres_user" \
  --dbname "$target_database" \
  --exit-on-error \
  --single-transaction \
  --no-owner \
  --no-privileges \
  <"$backup_file"

docker compose exec -T postgres vacuumdb \
  --username "$postgres_user" \
  --dbname "$target_database" \
  --analyze-only >/dev/null

database_created=0
trap - EXIT
printf 'Restore complete: database %s\n' "$target_database"
