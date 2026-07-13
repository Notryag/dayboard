# PostgreSQL Backup And Recovery

## Scope And Safety

PostgreSQL is Dayboard's source of truth. The production backup flow writes a compressed custom-
format dump and a SHA-256 checksum outside the Docker volume. Backups default to
`/var/backups/dayboard/postgres`, use owner-only permissions, and are retained for 14 days.

The restore script never overwrites the active database or an existing database. It always restores
into a new database, which keeps the current production database available for rollback.

Backups on the same host protect against an accidentally removed Docker volume, bad migrations, and
application-level data damage. They do not protect against total host or disk loss. Replicate the
backup directory to encrypted off-host storage when storage credentials and retention requirements
are available.

Never run `docker compose down -v`, delete `dayboard_postgres_data`, or drop the current production
database as part of a restore.

## Install The Daily Timer

Run these commands from the active production checkout:

```bash
cd /home/zx/dayboard
sudo install -d -m 0700 /var/backups/dayboard/postgres
sudo install -m 0644 deploy/systemd/dayboard-postgres-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/dayboard-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dayboard-postgres-backup.timer
sudo systemctl list-timers dayboard-postgres-backup.timer
```

The timer runs once a day at approximately 03:15 local time. `Persistent=true` runs a missed backup
after the server returns, and the randomized delay avoids requiring an exact execution minute.
Application containers remain owned by Docker Compose; systemd only schedules the one-shot backup.

The service template sets `DAYBOARD_BACKUP_RETENTION_DAYS=14`. Change that value in the installed
service unit, then run `systemctl daemon-reload`, if production needs a different local retention
period.

## Create And Verify A Backup

Create one immediately after installing the timer:

```bash
cd /home/zx/dayboard
sudo systemctl start dayboard-postgres-backup.service
sudo systemctl status dayboard-postgres-backup.service --no-pager
sudo ls -lah /var/backups/dayboard/postgres
sudo journalctl -u dayboard-postgres-backup.service -n 50 --no-pager
```

The service must produce both files:

```text
dayboard-postgres-YYYYMMDDTHHMMSSZ.dump
dayboard-postgres-YYYYMMDDTHHMMSSZ.dump.sha256
```

The script first asks PostgreSQL to validate the dump catalog, then atomically publishes the dump
and checksum. It logs file paths but does not log database credentials or row contents.

Run a restore rehearsal after installation, after changing PostgreSQL versions, and periodically:

```bash
cd /home/zx/dayboard
sudo deploy/scripts/postgres-restore-rehearsal.sh
```

The rehearsal verifies the checksum, restores the newest backup into a temporary database, checks
that public tables and the Alembic version exist, and removes the temporary database. It does not
stop or modify the production application database.

## Recover Production

Use this procedure only when production data must be replaced with a known backup. Choose a unique
database name and keep the old database until the recovered application has been accepted.

1. Record the current `POSTGRES_DB` value and the selected backup path.
2. Stop writers while leaving PostgreSQL running.

```bash
cd /home/zx/dayboard
sudo systemctl stop dayboard-postgres-backup.timer
sudo docker compose stop api worker web
```

3. Restore into a new database. The checksum file must be beside the dump.

```bash
sudo deploy/scripts/postgres-restore.sh \
  /var/backups/dayboard/postgres/dayboard-postgres-YYYYMMDDTHHMMSSZ.dump \
  dayboard_recovered_YYYYMMDD
```

4. Change only `POSTGRES_DB` in `/home/zx/dayboard/.env` to the new database name. Do not replace
   the rest of `.env` or expose its contents in shell history or logs.
5. Recreate the PostgreSQL container so its environment and health check use the recovered database,
   then start the application containers.

```bash
sudo docker compose up -d postgres
sudo docker compose up -d api worker web
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3001/dayboard
```

6. Inspect API and worker logs, verify authentication, and inspect representative calendar and task
   data before resuming normal operation.
7. Restart the timer only after production acceptance.

```bash
sudo systemctl start dayboard-postgres-backup.timer
sudo systemctl list-timers dayboard-postgres-backup.timer
```

To roll back, stop API, worker, and web; restore the original `POSTGRES_DB` value in `.env`; and run
the same Compose start and health commands. Do not drop either database until the recovery decision
is final and an additional verified backup exists.

## Troubleshooting

Inspect the one-shot service and timer without printing `.env`:

```bash
sudo systemctl status dayboard-postgres-backup.service --no-pager
sudo systemctl status dayboard-postgres-backup.timer --no-pager
sudo journalctl -u dayboard-postgres-backup.service -n 100 --no-pager
cd /home/zx/dayboard && sudo docker compose ps postgres
```

An interrupted dump remains hidden under a dot-prefixed temporary filename and is removed by the
script. An interrupted restore removes the newly created incomplete database. A checksum failure
must be treated as an unusable backup; select another dump instead of bypassing verification.
