#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${DAYBOARD_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
BACKUP_DIR="${DAYBOARD_BACKUP_DIR:-/var/backups/dayboard/postgres}"

if [[ $# -gt 1 ]]; then
  printf 'Usage: %s [BACKUP_FILE]\n' "$(basename "$0")" >&2
  exit 2
fi

if [[ $# -eq 1 ]]; then
  backup_file="$1"
else
  backup_file="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'dayboard-postgres-*.dump' | sort | tail -n 1)"
fi

if [[ -z "${backup_file:-}" ]]; then
  printf 'No PostgreSQL backup found in %s\n' "$BACKUP_DIR" >&2
  exit 1
fi

target_database="dayboard_restore_check_$(date -u +%Y%m%dT%H%M%SZ)_$$"
postgres_user=""
database_created=0

cleanup() {
  status=$?
  if [[ $database_created -eq 1 ]]; then
    cd "$PROJECT_DIR"
    docker compose exec -T postgres dropdb \
      --username "$postgres_user" \
      --if-exists \
      --force \
      "$target_database" >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT

"$SCRIPT_DIR/postgres-restore.sh" "$backup_file" "$target_database"
database_created=1

cd "$PROJECT_DIR"
postgres_user="$(docker compose exec -T postgres sh -ceu 'printf %s "$POSTGRES_USER"')"
table_count="$(
  docker compose exec -T postgres psql \
    --username "$postgres_user" \
    --dbname "$target_database" \
    --tuples-only \
    --no-align \
    --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
)"
migration_version="$(
  docker compose exec -T postgres psql \
    --username "$postgres_user" \
    --dbname "$target_database" \
    --tuples-only \
    --no-align \
    --command 'SELECT version_num FROM alembic_version'
)"

if [[ ! "$table_count" =~ ^[1-9][0-9]*$ ]]; then
  printf 'Restore rehearsal found no public tables\n' >&2
  exit 1
fi
if [[ -z "$migration_version" ]]; then
  printf 'Restore rehearsal found no Alembic migration version\n' >&2
  exit 1
fi

docker compose exec -T postgres dropdb \
  --username "$postgres_user" \
  --if-exists \
  --force \
  "$target_database"
database_created=0
trap - EXIT

printf 'Restore rehearsal passed: %s public tables, migration %s\n' \
  "$table_count" "$migration_version"
