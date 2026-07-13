#!/usr/bin/env bash

set -Eeuo pipefail

umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${DAYBOARD_PROJECT_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
BACKUP_DIR="${DAYBOARD_BACKUP_DIR:-/var/backups/dayboard/postgres}"
RETENTION_DAYS="${DAYBOARD_BACKUP_RETENTION_DAYS:-14}"

if [[ ! "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  printf 'DAYBOARD_BACKUP_RETENTION_DAYS must be a non-negative integer\n' >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || {
  printf 'docker is required\n' >&2
  exit 1
}
command -v flock >/dev/null 2>&1 || {
  printf 'flock is required\n' >&2
  exit 1
}
command -v sha256sum >/dev/null 2>&1 || {
  printf 'sha256sum is required\n' >&2
  exit 1
}

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"

exec 9>"$BACKUP_DIR/.backup.lock"
if ! flock -n 9; then
  printf 'Another PostgreSQL backup is already running\n' >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
filename="dayboard-postgres-$timestamp.dump"
final_dump="$BACKUP_DIR/$filename"
final_checksum="$final_dump.sha256"
temporary_dump="$(mktemp "$BACKUP_DIR/.${filename}.XXXXXX")"
temporary_checksum="$(mktemp "$BACKUP_DIR/.${filename}.sha256.XXXXXX")"

cleanup() {
  rm -f "$temporary_dump" "$temporary_checksum"
}
trap cleanup EXIT

if [[ -e "$final_dump" || -e "$final_checksum" ]]; then
  printf 'Backup already exists for timestamp %s\n' "$timestamp" >&2
  exit 1
fi

cd "$PROJECT_DIR"

docker compose exec -T postgres sh -ceu '
  pg_isready --quiet --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"
  exec pg_dump \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges
' >"$temporary_dump"

if [[ ! -s "$temporary_dump" ]]; then
  printf 'PostgreSQL produced an empty backup\n' >&2
  exit 1
fi

docker compose exec -T postgres pg_restore --list <"$temporary_dump" >/dev/null

checksum="$(sha256sum "$temporary_dump" | cut -d ' ' -f 1)"
printf '%s  %s\n' "$checksum" "$filename" >"$temporary_checksum"
chmod 0600 "$temporary_dump" "$temporary_checksum"
mv "$temporary_dump" "$final_dump"
mv "$temporary_checksum" "$final_checksum"

find "$BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'dayboard-postgres-*.dump' -o -name 'dayboard-postgres-*.dump.sha256' \) \
  -mtime "+$RETENTION_DAYS" -delete

trap - EXIT
printf 'Backup complete: %s\n' "$final_dump"
