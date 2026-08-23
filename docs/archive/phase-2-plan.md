# Phase 2 计划：面向公众的产品就绪

> 已归档：以下里程碑状态和后续工作列表属于历史记录，不得用于指导当前实现。当前里程碑请使用[项目状态](../PROJECT_STATE.md)。

## 产品目标

将 Dayboard 从共享用户的技术 MVP 发展为可发布产品，使任何人都能创建账号并安全管理自己的日程和提醒。

Phase 1 证明了 Agent loop。Phase 2 主要不是 Agent-capability 阶段，而是补齐实际使用所需的产品边界：identity、ownership、
personal settings、reminder delivery、abuse protection，以及最小可检查体验。

公开自助注册是有意提供的产品能力，生产环境必须保持可用。发布保护应来自 identity isolation、endpoint-specific rate limits、
login abuse protection、provider budgets 和 operational visibility，而不是 invitation gate。

## 当前产品评估

自然语言 scheduling backend 已形成 MVP 质量的闭环：

- 创建、查找、修改、完成和取消 calendar entries 与 tasks；
- 从一条消息执行多个指令；
- 使用结构化选项澄清含糊目标；
- 持久化 conversations 和有界 Agent context；
- 暴露持久化的 Run progress 和安全的 tool observability；
- 使用 tenant scoping、idempotency、optimistic concurrency 和 audit fields 保护写入；
- 在生产环境运行 API、worker、PostgreSQL、Redis、migrations、usage accounting 和 budgets。

Password authentication、self-service registration、tenant ownership 和 same-site web/API deployment 已在生产环境运行。
scheduling backend 超前于产品界面：用户仍需要可检查的 calendar/task view、可重新连接的 Run execution、稳定的 error handling
以及发布级 abuse controls。reminder inbox 尚未渲染，browser voice capture 也尚未连接。

## 里程碑顺序

### P2.1 真实 Identity 和 Ownership

状态：backend、web session flow、isolation acceptance 和 production enablement 已完成。

已完成：

- 在 FastAPI 中实现 username/password registration 和 login；
- 在 `HttpOnly` cookies 中使用 Argon2id password hashes 和可撤销的 server-side sessions；
- Dayboard users、memberships、timezone/locale profiles 和 external-identity extension point；
- 从 sessions 和 memberships 解析可信 `TenantContext`；
- 最小 web registration、login、logout、session recovery 和 credentialed SSE；
- 支持 optional-email password recovery，使用 single-use expiring tokens、SMTP delivery，并在重置后全局撤销 sessions；
- 针对 threads 以及 Run status、events、streaming 和 cancellation 的双用户 ownership acceptance。

剩余：

- 在下一个 release gate 运行扩展的 same-tenant/different-owner acceptance set；

生产启动会拒绝 development auth 或 insecure cookies。Registration、login、command 和 voice endpoints 分别使用 Redis-backed
abuse limits，同时不禁用 public registration。conversations、Runs、calendar entries、tasks、transcripts、reminders 和
provider usage 的 repository access 同时受 tenant 和 owner 约束。repository audit 后，Run 和 provider-usage boundaries 已收紧。

完成意味着两个用户无法读取、修改、stream 或推断彼此的数据，且生产部署不会意外以 development-auth mode 启动。

Backend acceptance 现在覆盖 threads、Run status、durable Run events、SSE 和 cancellation 的 password-session isolation。
same-site web/API deployment 和 coordinated password-auth release 已完成。Password recovery 已实现；生产 delivery 还需要
SMTP configuration。

### P2.2 提醒投递

状态：durable in-app delivery foundation 已完成；user-visible inbox 和 external provider 待完成。

已完成：

- 将 fixed-duration reminder intent 规范化为 scheduled delivery time；
- 使用 PostgreSQL outbox 同步 create、reschedule、completion 和 cancellation；
- 通过现有 worker 使用 `FOR UPDATE SKIP LOCKED` claim 到期的 in-app reminders；
- 持久化 tenant-scoped status、attempts、provider IDs 和 delivery timestamps；
- 通过 `GET /api/reminders` 暴露 delivery records。

剩余：

- 渲染最小 in-app reminder inbox；
- 选择一个适合中国目标用户的 external provider；
- 实现 provider acknowledgement、retry scheduling 和 terminal failure acceptance。

完成意味着创建的 reminder 会产生一个可观察的 notification，或一条明确且可恢复的 failure record。

PostgreSQL outbox、固定时长规范化、来源替换/取消规则、租户范围查询 API、Worker 认领
和幂等的 `in_app` delivery 已实现。剩余工作是最小 web notification surface，以及在选择产品渠道后增加一个带 retry 和
acknowledgement acceptance 的 external provider adapter。

### P2.3 最小可用体验

- 暴露 tenant-scoped、cursor-paginated calendar 和 task query APIs（已完成）；
- 使用这些 APIs 展示 today、tomorrow 和 open-task views（已完成）；
- 根据 structured results 渲染已创建/已修改的对象；
- 保留 structured clarification controls；
- 为 provider-unavailable failures 提供清晰的 retry behavior；
- 将 browser recording 连接到 transcription、editable text confirmation 和 normal command submission（已使用可选择的
  Cloudflare Workers AI 和 Alibaba Cloud adapters 实现；仍需使用非敏感中文录音完成 authenticated browser acceptance）。

本里程碑应保持 TypeScript API 和 feature logic 可复用，以支持计划中的 visual redesign。不包含 brand polish 或大型
组件系统迁移。

## 明确延期

- 多 Agent 编排；
- 外部日历同步；
- organization administration 和 billing UI；
- 同时支持多个 notification channels；
- 原生移动应用；
- 详细视觉重设计；
- 按步骤显示 token 成本的 UI。

## 近期后续工作

1. 增加 release protection：production auth fail-closed、endpoint-specific limits、login abuse protection 和 reproducible deployment checks，同时保持 registration open。
2. 为注册用户构建最小可检查的 calendar/task experience。
3. 增加 Run reconnection 和 stable API errors，使用户能从 network 和 provider faults 中恢复。
4. 将 reminder UI 和 external provider work 延后，直到它们成为产品优先事项。

## 运维验收

无需读取私有用户内容，也必须能够追踪 support report。API logs 和 durable Run events 应允许 operator 跟踪：

```text
request_id -> authenticated user/tenant -> thread_id -> run_id -> runtime/tool event -> object id
```

Logs 记录 status、latency、provider request IDs（如可用）、safe error types 和 correlation IDs。不记录 passwords、session
tokens、cookies、raw audio 或完整 command text。
