# 项目状态

本文件有意保持简短，是面向发布的摘要，而不是架构文档或实现过程记录。当前事实位于 [current](./current/README.md)，决策位于
[adr](./adr/README.md)，已过期的计划位于 [archive](./archive/README.md)。

## 当前版本

- 开发线：`0.3.x`；最新部署发布标签：`v0.3.25`。
- 产品：位于 `dayboard.selfapi.art` 根路径的自助式 Dayboard Web 应用，提供同站点 FastAPI API。
- 运行时：由 Docker Compose 管理 PostgreSQL、Redis、FastAPI、arq Worker 和 Next.js。
- 调度策略：任何可解析的日期或时间都会创建日历条目；仅日期条目使用原生 `anytime` 形状；没有时间锚点的操作会创建任务。
- 实时执行：North `RunExecutor` 通过 Redis Streams 发布规范化分块；FastAPI 暴露投影后的 SSE 事件；PostgreSQL 保存权威 Run 和会话状态。
- 前端：Next.js、OpenAPI 生成的 `openapi-fetch`、TanStack Query、shadcn/ui 原语，以及经过验证的可区分 Run 事件 reducer。

## 已完成

- 添加已认证的提醒中心，支持持久化未读状态、未读计数、按调度来源导航、失败投递重试、前台浏览器 Notifications 以及按租户隔离的 Reminder API。
- 添加自动 FastAPI 到 Web 的 OpenAPI 漂移强制检查，并为 Auth、Voice、
  Schedule、Reminder、Conversation 和 Run 恢复、TanStack Query 分页/失效处理，以及经过验证的可区分 SSE 事件边界。
- 添加关键 Playwright 浏览器门禁，包括确定性 SSE、活动 Run 恢复、澄清恢复、乐观编辑/撤销和固定音频语音覆盖。
- 扩展 CI 和发布质量任务，运行完整 PostgreSQL API 套件和浏览器 E2E。
- 添加版本化的 128 案例中文调度 Agent Eval，包含 PostgreSQL 权威调度断言、类型化澄清 CAS 恢复覆盖、类别发布门禁，以及质量、安全、延迟、缓存和 token 指标。
- 支持密码注册/登录、服务器会话、密码恢复、租户/所有者隔离和端点级滥用限制。
- 支持日历条目和任务的自然语言创建、搜索、改期、取消、完成、多命令执行和结构化澄清。
- 支持定时及 `anytime` 日历条目、乐观并发、幂等 Agent 写入、冲突检查、提醒同步和租户范围的调度查询 API。
- 支持持久化 Thread、有界上下文、压缩摘要、排队 Run、取消、过期 Run 恢复、提供商使用量结算以及请求/Run/工具关联。
- 支持带重放游标的 Redis StreamBridge 传递、重放间隙恢复、安全工具结果投影、持久化会话部分和可重连浏览器 SSE。
- 引入 `agent_platform` 包，将可信身份及与存储无关的 Conversation/Run 规范和服务移出 Dayboard 产品命名空间。
- 添加显式共享 Unit of Work、原子幂等命令提交、回滚安全的声明复用，以及并发安全的持久化 Run 事件序列分配。
- 添加版本化可恢复 Interaction、Dayboard 所有的类型化澄清载荷、安全生成的 Web 状态规范，以及带重试恢复的原子比较并消费式续接提交。
- 用 Platform 所有的版本化 Presentation envelope、Dayboard 所有的已验证调度载荷、生成的 Web 历史类型和一致的实时/刷新调度卡恢复，替换无版本助手消息元数据。
- 通过受限的 `active | archived` 状态、显式 `is_primary`、一次性数据迁移和仅活动 Thread 命令提交，将 Conversation Thread 生命周期与主身份分离，同时保留归档历史读取和幂等重试。
- 使旧 JSON 存储与 ORM 的 JSONB 规范一致，将 North checkpoint 表声明为外部所有，并将 `alembic check` 设为 CI schema 漂移门禁。
- 将发布前的 12 个 Alembic 修订压缩为一个与 ORM 对齐的初始 schema，同时保留已部署的 `202607230007` head 身份，使现有开发数据库和全新安装共享一条迁移路径，无需兼容分支或手动 stamp。
- 用 Platform 所有的 Event Extension envelope 以及类型化 North model/tool 和 Platform failure/interaction-state 载荷，替换无版本持久化 Run 事件元数据。
- 添加产品中立的 Platform Run 执行协调器，支持原子终态持久化、Dayboard 所有的 North driver 和结果投影器、数据库权威的仅 `run_id` 作业，并移除已被取代的执行兼容路径。
- 添加产品所有的 Scheduling Unit of Work：应用服务现在使用领域存储 port，SQLAlchemy repository 返回领域对象，日历/任务变更在 API 或 Agent 边界与 Reminder Outbox 替换原子提交。
- 添加独立的产品所有 Reminder Unit of Work：inbox 和 Worker 服务使用传递及 source-projection port，队列状态保持私有，过期日历通知与已取消来源区分，inbox 条目使用当前权威来源快照。
- 添加产品所有的 Voice Unit of Work 和提供商 port：应用代码接收领域转写，租户范围 repository 负责 ORM 映射，外部 ASR 提供商运行期间不会保持数据库事务打开。
- 添加 Dayboard 所有的 Account Recovery Unit of Work：重置签发/消费返回无存储记录，API 边界负责提交/回滚，User 行锁串行化 token 替换、密码重置和会话撤销。登录在数据库事务外验证未锁定的凭据快照，然后短暂加锁并重新验证，再创建 Session。
- Provider Usage 通过狭窄的结算 port。其 SQLAlchemy adapter 负责一个独立短事务，所有者范围的插入支持并发和幂等，ORM 行留在 repository 中，结算失败不能替换权威的 Run 终态。
- 将 Platform 和 Run 构造移至显式 composition root：FastAPI dependency 构建无存储命令服务，Worker 为每个 Run 构建一个 North driver，运行时日志事件使用新的 Platform Unit-of-Work session，而不是共享执行 session。
- 提供响应式会话/日视图 UI、移动视图直接拖动、流式搜索结果行、语音录制和 ASR adapter、直接调度编辑、深色模式、设置抽屉、生成的 API schema，以及 600 行前端源码约束。
- 提供带校验和、保留策略且成功完成恢复演练的每日本地 PostgreSQL 备份。

## 下一里程碑

架构加固和公开发布完成：

1. 使用非敏感中文调度短语完成 Chrome 和 Safari 语音验收。
2. 提供商预算窗口允许后，完成相对日期、提醒以及变更/取消流程的实时 Agent 验收。
3. 测量 Northgate 提示词缓存效果，只有所有生产流量都在无直接提供商回退的情况下使用 gateway 后，才将范围化 provider-token 策略移入 gateway。
4. 添加加密的异地主机 PostgreSQL 备份复制，并演练从该副本恢复。

详细的进行中 token 和 gateway 工作记录在[路线图](./plans/roadmap.md)中。

## 已知问题

- 已安装 PWA 的后台通知有意延后；浏览器 Notifications 要求已认证 Web 应用处于活动状态。
- v0.3.22 基准单写 Run 在一次模型调用中使用 2,069 个 token，其中包括 1,536 个缓存输入 token，成本为 $0.000977。在每种行为建立可复现的生产基线前，更广泛的逐案例预算仍有意未设置。
- North 当前在 `ask_clarification` 后、返回其类型化结果前会多进行一次不必要的模型调用。v0.3.25 `same-01` 澄清 Run 通过三次调用使用了 11,304 个 token；[north-agent#1](https://github.com/Notryag/north-agent/issues/1) 追踪在澄清命令处终止 Run。
- Dayboard 仍负责 provider-token 准入；Northgate 尚未为所有流量执行租户/用户/模型范围预算。
- 调度默认使用可信的 `Asia/Shanghai`；不支持显式外国时区转换。
- 浏览器语音行为有提供商 smoke 覆盖，但尚未覆盖完整 Chrome/Safari 发布矩阵。
- 正在进行的 ASR 请求中 API 进程突然终止，可能使审计转写停留在 `processing`；普通请求取消会完成为 `failed`，但过期进程恢复要等 Voice 执行迁移到持久化异步生命周期后进行。
- 密码重置邮件在 token 事务提交后尽力投递。并发重置请求可能乱序投递；在引入持久化邮件 Outbox 前，只有最新 token 保持有效。
- Worker 在 Provider Usage 结算前硬退出可能遗漏汇总；在 PostgreSQL 提交后但 Redis 预算协调前崩溃，可能使预留值不准确；持久化使用量恢复仍待完成。
- 备份仅在本地主机；加密异地主机复制待完成。

## 发布检查

在打标签或部署发布版本前：

- [ ] 确认 `main` 包含预期迁移和生成的 OpenAPI schema。
- [ ] 在 `apps/web` 中运行 `npm run api:types:check`、`npm run lint`、`npm run typecheck` 和 `npm run build`。
- [ ] 针对名称以 `_test` 结尾的数据库运行 Ruff 和完整 PostgreSQL API 套件。
- [ ] 在不使用截图或真实麦克风的情况下运行关键 Playwright E2E 套件。
- [ ] 针对测试数据库运行 Alembic upgrade，并检查新迁移生成的 SQL。
- [ ] 当变更影响提示词/工具行为时，运行定向 Agent 验收程序。
- [ ] 在重新创建容器前构建替换 Docker 镜像。
- [ ] 验证 API、Worker、PostgreSQL 和 Redis 健康状态以及 `/dayboard` HTTP 响应。
- [ ] 确认备份为最新，且不要使用 `docker compose down -v`。

命令和回滚流程见 [operations/deploy.md](./operations/deploy.md)；测试策略见
[engineering-guidelines.md](./engineering-guidelines.md)。
