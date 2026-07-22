# Docker 部署

Dayboard 生产应用使用仓库根目录的 Compose 文件管理；PostgreSQL 和 Redis 由独立的基础设施
Compose 管理，Dayboard 通过 `docker-compose.platform.yml` 接入可配置的共享外部网络：

```text
Nginx
  -> 127.0.0.1:8000 -> API
  -> 127.0.0.1:3001 -> Web

platform-infra Compose
  -> PostgreSQL、Redis

Dayboard Docker Compose
  -> API、Worker、Web
```

生产工作目录固定为 `/home/zx/dayboard`。不要从其他代码副本启动同名服务，也不要为
API、Worker 或 Web 增加第二套进程管理器。

## 前置条件

- Docker Engine 与 Docker Compose 插件
- 一个 HTTPS 域名和 Nginx
- OpenAI 兼容模型接口
- 可选的 Cloudflare Workers AI 或阿里云 ASR 凭据

容器端口只绑定到 `127.0.0.1`，PostgreSQL 和 Redis 不应暴露到公网。

## 配置环境变量

从模板创建本地配置：

```bash
cd /home/zx/dayboard
cp .env.example .env
chmod 600 .env
```

生产环境至少需要检查以下配置：

```dotenv
DAYBOARD_ENV=production
DAYBOARD_AUTH_MODE=password
DAYBOARD_AUTH_COOKIE_SECURE=true
DAYBOARD_DEFAULT_TIMEZONE=Asia/Shanghai

POSTGRES_DB=dayboard
POSTGRES_USER=dayboard
POSTGRES_PASSWORD=replace-with-a-strong-password

APP_MODEL_NAME=openai:gpt-4o-mini
OPENAI_BASE_URL=https://your-openai-compatible-gateway/v1
OPENAI_API_KEY=replace-with-a-real-secret
DAYBOARD_NORTHGATE_METADATA_ENABLED=false
```

接入 Northgate 时，`OPENAI_BASE_URL` 使用 gateway 的 OpenAI prefix，
`OPENAI_API_KEY` 使用 Northgate application key，并显式启用可信归因：

```dotenv
OPENAI_BASE_URL=http://northgate:8080/v1/gateways/dayboard/openai
OPENAI_API_KEY=replace-with-a-northgate-application-key
DAYBOARD_NORTHGATE_METADATA_ENABLED=true
```

API 和 Worker 必须使用相同配置。回滚时恢复原供应商 base URL 和 key，并将 metadata
开关设为 `false`；不要把 Northgate metadata header 发送到其他供应商。

生产 canary 不修改上述全局 OpenAI 配置，而是保留原供应商连接并设置独立的 Northgate
连接和 tenant allowlist：

```dotenv
DAYBOARD_NORTHGATE_BASE_URL=http://northgate:8080/v1/gateways/dayboard/openai
DAYBOARD_NORTHGATE_APPLICATION_KEY=replace-with-a-northgate-application-key
DAYBOARD_NORTHGATE_CANARY_TENANT_IDS=00000000-0000-0000-0000-000000000001
```

只有可信 tenant ID 命中 allowlist 的 run 使用 Northgate，并自动附带 tenant、user 和
run metadata。其他 tenant 继续使用 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`。清空 allowlist
并重建 API/Worker 容器即可回滚 canary，不依赖 Northgate 控制面。

使用 Cloudflare 语音识别时再配置：

```dotenv
DAYBOARD_ASR_PROVIDER=cloudflare
CLOUDFLARE_ACCOUNT_ID=replace-with-your-account-id
CLOUDFLARE_API_TOKEN=replace-with-a-workers-ai-token
CLOUDFLARE_ASR_MODEL=@cf/openai/whisper-large-v3-turbo
```

启用邮箱找回密码时配置 SMTP。没有配置 `DAYBOARD_SMTP_HOST` 和
`DAYBOARD_MAIL_FROM_ADDRESS` 时，注册和登录不受影响，找回密码接口会明确返回暂不可用：

```dotenv
DAYBOARD_PUBLIC_WEB_URL=https://your-host/dayboard
DAYBOARD_PASSWORD_RESET_TTL_SECONDS=1800
DAYBOARD_SMTP_HOST=smtp.example.com
DAYBOARD_SMTP_PORT=587
DAYBOARD_SMTP_USERNAME=replace-with-smtp-user
DAYBOARD_SMTP_PASSWORD=replace-with-smtp-password
DAYBOARD_SMTP_SECURITY=starttls
DAYBOARD_MAIL_FROM_ADDRESS=no-reply@example.com
DAYBOARD_MAIL_FROM_NAME=Dayboard
```

注册邮箱保持可选；只有已经绑定邮箱的账号可以自助找回密码。SMTP 使用隐式 TLS 时将
`DAYBOARD_SMTP_SECURITY` 设为 `ssl`，直接可信内网连接才使用 `plain`。

真实凭据只能保存在 `.env` 或密钥管理服务中，不能提交到 Git、写入 Dockerfile 或打印到
日志。修改 `NEXT_PUBLIC_DAYBOARD_API_BASE_URL` 或 `NEXT_PUBLIC_DAYBOARD_BASE_PATH` 后必须重新
构建 Web 镜像，因为这两个变量会被编译进浏览器资源。

## 首次启动

先校验配置，再构建并启动所有服务：

```bash
cd /home/zx/dayboard
docker compose config --quiet
docker compose build api worker web
docker compose up -d
docker compose ps
```

API 容器启动时会自动执行 `alembic upgrade head`。不要在生产宿主机额外启动一份迁移、
FastAPI、arq 或 Next.js 进程。

## 自动部署

推送语义化版本标签后，[GitHub Actions workflow](../.github/workflows/deploy.yml) 自动执行：

1. API Ruff 检查、Alembic 升级和完整 PostgreSQL 测试；
2. Web ESLint、TypeScript、生产构建和关键 Playwright E2E；
3. 构建 API、Web 镜像并以 Git commit SHA 和版本号为标签推送到 GHCR；
4. 通过 SSH 连接服务器，拉取对应镜像；
5. 备份 PostgreSQL，使用新 API 镜像执行迁移；
6. 替换 API、Worker、Web 容器并执行健康检查。

自动部署会先验证版本标签确实指向 workflow 构建的 commit，再让服务器仓库以 detached HEAD
检出该不可变 commit。部署不依赖构建期间 `main` 是否继续前进，因此主线上的后续提交不会
使一个已经完成质量检查和镜像构建的版本失败。服务器工作树表示当前发布版本，不表示实时
`main`；需要检查主线时使用 `git log origin/main`，不要在服务器上直接提交。

API 和 Worker 使用同一个 API 镜像。自动部署使用
[`docker-compose.deploy.yml`](../docker-compose.deploy.yml) 覆盖应用镜像，服务器不会再次构建
源码，并使用 `docker-compose.platform.yml` 接入共享基础设施。`concurrency` 保证同一时间只有
一个生产部署运行。

普通 `main` push 和 Pull Request 只触发 [CI workflow](../.github/workflows/ci.yml)，不会部署。
准备发布时，确保 `main` 已推送且工作区干净，再创建带说明的版本标签：

```bash
git switch main
git pull --ff-only
git tag -a v0.2.0 -m "Dayboard v0.2.0"
git push origin v0.2.0
```

标签必须指向当前 `main` 最新提交。已经推送的版本标签不要移动或覆盖；下一次发布使用
`v0.2.1` 或 `v0.3.0`。

在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 中配置：

| Secret | 内容 |
| --- | --- |
| `DEPLOY_HOST` | SSH 主机名，例如 `www.selfapi.art` |
| `DEPLOY_USER` | 受限部署用户，例如 `zx` |
| `DEPLOY_SSH_KEY` | 仅供 Actions 使用的 Ed25519 私钥 |
| `DEPLOY_KNOWN_HOSTS` | 已核验的 SSH 主机公钥记录 |

对应公钥必须加入服务器部署用户的 `~/.ssh/authorized_keys`。部署用户需要读取仓库、运行
Docker Compose 和以免密 sudo 调用数据库备份脚本的权限。GHCR 登录使用当前 workflow 的
短期 `GITHUB_TOKEN`，不需要保存长期 Registry Token。

`production` GitHub Environment 可以增加审批人和分支保护。

## 手动更新

自动部署异常时，保留源码构建流程作为回退手段。先拉取和构建，构建成功后再替换容器：

```bash
cd /home/zx/dayboard
git status --short --branch
git pull --ff-only
docker compose config --quiet
docker compose build api worker web
docker compose up -d
docker compose ps
```

只修改单个应用时可以缩小更新范围：

```bash
# 仅更新 Web
docker compose build web
docker compose up -d --no-deps web

# 更新 API 与 Worker；两者共用 API 镜像
docker compose build api worker
docker compose up -d --no-deps api worker
```

修改数据库迁移、Compose 依赖或共享环境变量时应执行全量 `docker compose up -d`，不要使用
`--no-deps` 跳过依赖协调。

## 验证部署

```bash
cd /home/zx/dayboard
docker compose ps
curl -fsS http://127.0.0.1:8000/health
curl -fsSL -o /dev/null -w 'Web HTTP %{http_code}\n' \
  http://127.0.0.1:3001/dayboard/
curl -fsSL -o /dev/null -w 'Public HTTP %{http_code}\n' \
  https://your-host/dayboard/
```

API 健康响应中的 `database`、`redis` 和 `worker` 都应为 `ok`，Web 最终响应应为 HTTP 200。
还应在浏览器中验证登录、发送一条文字命令和打开日视图。启用语音后，再验证已登录请求
`GET /dayboard-api/api/voice/capabilities` 返回 `available: true`。

## 查看日志

```bash
docker compose logs --tail=100 api worker web
docker compose logs -f api worker
docker compose events
```

先用 `docker compose ps` 确认失败的服务，再只读取相关容器日志。不要输出整个 `.env` 排查
问题。

## Nginx

仓库中的 [dayboard-locations.conf](../deploy/nginx/dayboard-locations.conf) 提供路径代理模板：

- `/dayboard-api/` -> `127.0.0.1:8000`
- `/dayboard` 和 `/dayboard/` -> `127.0.0.1:3001`

将模板包含到 HTTPS `server` 块后执行：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

只有容器健康且本机端口验证通过后才能重载 Nginx。生产 Web 构建默认使用：

```text
NEXT_PUBLIC_DAYBOARD_API_BASE_URL=/dayboard-api
NEXT_PUBLIC_DAYBOARD_BASE_PATH=/dayboard
```

Web 和 API 保持同站点，才能稳定使用 `HttpOnly`、`SameSite=Lax` 的登录会话 Cookie。

## 数据安全

PostgreSQL 数据保存在 `dayboard_postgres_data` 命名卷中，Redis 数据保存在
`dayboard_redis_data`。生产环境禁止执行：

```text
docker compose down -v
docker volume rm dayboard_dayboard_postgres_data
```

普通停止使用 `docker compose stop`，重新创建应用容器不会删除命名卷。数据库升级、恢复或
其他破坏性操作前，先阅读 [PostgreSQL 备份与恢复](./postgres-backup.md) 并确认存在可用备份。
备份定时器只负责调用 Compose 内的 PostgreSQL 工具，不管理应用进程。

## 常用运维命令

```bash
# 服务状态
docker compose ps

# 重启单个应用服务
docker compose restart web

# 重新构建并替换单个服务
docker compose build web
docker compose up -d --no-deps web

# 停止或恢复全部服务，不删除数据卷
docker compose stop
docker compose start

# 查看 Compose 最终配置，不输出完整环境值
docker compose config --services
```

Compose 的 `restart: unless-stopped` 负责宿主机重启后的服务恢复。应用生命周期统一使用
Docker Compose，不再维护宿主机直跑应用的部署流程。
