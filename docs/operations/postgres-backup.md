# PostgreSQL 备份与恢复

## 范围与安全

PostgreSQL 是 Dayboard 的事实来源。生产备份流程在 Docker 卷之外写入压缩的 custom-
format dump 和 SHA-256 校验和。备份默认位于
`/var/backups/dayboard/postgres`，使用仅所有者可访问的权限，并保留 14 天。

恢复脚本绝不会覆盖活动数据库或已有数据库。它始终恢复到新数据库，从而保留当前生产数据库以便回滚。

同一主机上的备份可以防止 Docker 卷被误删、迁移错误和应用层数据损坏，但无法防止主机或磁盘完全丢失。当存储凭据和保留要求具备后，将备份目录复制到加密的异地主机存储。

恢复时绝不要运行 `docker compose down -v`、删除 `dayboard_postgres_data` 或删除当前生产数据库。

## 安装每日定时器

在活动生产 checkout 中运行以下命令：

```bash
cd /home/zx/dayboard
sudo install -d -m 0700 /var/backups/dayboard/postgres
sudo install -m 0644 deploy/systemd/dayboard-postgres-backup.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/dayboard-postgres-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now dayboard-postgres-backup.timer
sudo systemctl list-timers dayboard-postgres-backup.timer
```

定时器每天本地时间约 03:15 运行一次。`Persistent=true` 会在服务器恢复后执行错过的备份，随机延迟避免要求精确的执行分钟。应用容器仍由 Docker Compose 管理；systemd 只负责安排一次性备份。

服务模板设置 `DAYBOARD_BACKUP_RETENTION_DAYS=14`。如果生产环境需要不同的本地保留周期，在已安装的 service unit 中修改该值，然后运行 `systemctl daemon-reload`。

## 创建并验证备份

安装定时器后立即创建一份备份：

```bash
cd /home/zx/dayboard
sudo systemctl start dayboard-postgres-backup.service
sudo systemctl status dayboard-postgres-backup.service --no-pager
sudo ls -lah /var/backups/dayboard/postgres
sudo journalctl -u dayboard-postgres-backup.service -n 50 --no-pager
```

服务必须生成以下两个文件：

```text
dayboard-postgres-YYYYMMDDTHHMMSSZ.dump
dayboard-postgres-YYYYMMDDTHHMMSSZ.dump.sha256
```

脚本首先请求 PostgreSQL 校验 dump 目录，然后原子发布 dump 和校验和。它记录文件路径，但不记录数据库凭据或行内容。

安装后、变更 PostgreSQL 版本后以及定期运行恢复演练：

```bash
cd /home/zx/dayboard
sudo deploy/scripts/postgres-restore-rehearsal.sh
```

演练校验校验和，将最新备份恢复到临时数据库，检查 public 表和 Alembic 版本存在，然后删除临时数据库。它不会停止或修改生产应用数据库。

## 恢复生产环境

仅当生产数据必须替换为已知备份时使用此流程。选择唯一的数据库名称，并保留旧数据库，直到恢复后的应用通过验收。

1. 记录当前 `POSTGRES_DB` 值和选定的备份路径。
2. 保持 PostgreSQL 运行，同时停止写入方。

```bash
cd /home/zx/dayboard
sudo systemctl stop dayboard-postgres-backup.timer
sudo docker compose stop api worker web
```

3. 恢复到新数据库。校验和文件必须与 dump 位于同一目录。

```bash
sudo deploy/scripts/postgres-restore.sh \
  /var/backups/dayboard/postgres/dayboard-postgres-YYYYMMDDTHHMMSSZ.dump \
  dayboard_recovered_YYYYMMDD
```

4. 仅将 `/home/zx/dayboard/.env` 中的 `POSTGRES_DB` 修改为新数据库名。不要替换 `.env` 其余内容，也不要在 shell 历史或日志中暴露其内容。
5. 重新创建 PostgreSQL 容器，使其环境和健康检查使用恢复后的数据库，然后启动应用容器。

```bash
sudo docker compose up -d postgres
sudo docker compose up -d api worker web
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3001/dayboard
```

6. 检查 API 和 Worker 日志，验证身份认证，并检查有代表性的日历和任务数据，然后恢复正常运行。
7. 只有生产验收通过后才重新启动定时器。

```bash
sudo systemctl start dayboard-postgres-backup.timer
sudo systemctl list-timers dayboard-postgres-backup.timer
```

回滚时，停止 API、Worker 和 Web；将 `.env` 中的 `POSTGRES_DB` 恢复为原值；然后运行相同的 Compose 启动和健康检查命令。在恢复决策最终确定且存在另一份已验证备份前，不要删除任一数据库。

## 故障排查

在不打印 `.env` 的情况下检查一次性服务和定时器：

```bash
sudo systemctl status dayboard-postgres-backup.service --no-pager
sudo systemctl status dayboard-postgres-backup.timer --no-pager
sudo journalctl -u dayboard-postgres-backup.service -n 100 --no-pager
cd /home/zx/dayboard && sudo docker compose ps postgres
```

中断的 dump 会以点号开头的临时文件名隐藏，并由脚本删除。中断的恢复会删除新创建的不完整数据库。校验和失败必须视为备份不可用；应选择另一份 dump，而不是绕过验证。
