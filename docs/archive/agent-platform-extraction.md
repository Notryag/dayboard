# 已归档的 Agent Application Platform 提取计划

状态：提取里程碑完成后归档<br>
归档日期：2026-08-23

本文件保留提取约束和里程碑记录，不得用于指导新的实现。当前所有权以[当前架构](../current/architecture.md)为准，
正在进行且取决于条件的工作见[路线图](../plans/roadmap.md)，相关决策仍记录在
[ADR-008](../adr/008-introduce-agent-application-platform.md) 和
[ADR-009](../adr/009-keep-platform-and-north-independent.md) 中。

## 层级契约

```text
Dayboard
  |---------------------> Agent Application Platform
  |                        reusable application capabilities
  |
  +---------------------> North
                           runtime primitives
```

未来的兄弟产品可以使用同一个 Platform。兄弟产品之间不得互相导入。上面的箭头表示源代码导入关系，
而不是运行时事件或返回值的流向。North 和 Agent Application Platform 是彼此独立的底层能力；Dayboard 注入的
`RunExecutionDriver` 负责桥接二者。这并不是有意强制形成 `Dayboard -> Platform -> North` 链路。

Platform 仍是一个逻辑层，但其内部职责分离如下：

```text
agent_platform/
  core/          framework-free contracts and state rules
  application/   transaction-scoped use cases
  ports/         storage, runtime, publishing, and projection interfaces
```

具体技术适配器不属于当前包。未来可选的适配器包可以在第二个产品证明存在相同持久化或运行时契约后，
向内依赖这些接口。这种结构可防止持久化和 North 集成细节成为可复用 Core 的依赖。

## 当前所有权映射

| 当前范围 | 当前所有者 | 目标所有者 | 迁移说明 |
| --- | --- | --- | --- |
| North agent loop, middleware, checkpoints, StreamBridge | North | North | 已由正确所有者负责 |
| 可信 `TenantContext` 契约 | Platform | Platform | 已提取；Dayboard 仅保留开发上下文构造 |
| Conversation thread/message/state 契约 | Platform | Platform | 已提取；原 Dayboard domain 模块已删除 |
| Conversation service | Platform | Platform | 已连同显式 Unit of Work 和 Interaction CAS 一起提取 |
| PostgreSQL Conversation repositories | Dayboard adapter | 当前由 Dayboard 负责；之后可选 Platform SQLAlchemy adapter | 不能仅凭一个已验证产品就迁移；需要第二个产品证明存在相同 schema 和事务契约 |
| Run 和 Run-event 契约 | Platform | Platform | 已提取；原 Dayboard domain 模块已删除 |
| Run lifecycle service | Platform | Platform | 已连同显式 Unit of Work 检查点一起提取 |
| PostgreSQL Run repositories | Dayboard adapter | 当前由 Dayboard 负责；之后可选 Platform SQLAlchemy adapter | 不能仅凭一个已验证产品就迁移；需要第二个产品证明存在相同 schema 和生命周期并发契约 |
| Command 幂等性 | Platform | Platform | 与 ORM 无关的 record、Store、校验、清理和回滚已完成 |
| Command 提交和分发 | Split | Split | Platform 负责原子提交；Dayboard 负责队列和产品执行 |
| 持久化消息 artifacts | Split | Split | 已实现：Platform 负责带版本的 envelope/lifecycle；Dayboard 负责并校验 schedule payloads |
| 澄清交互状态 | Split | Split | 已实现：Platform 负责 envelope/CAS；Dayboard 负责 typed payload 和 response projection |
| Voice/media ingestion 生命周期 | Dayboard boundary | Platform candidate | 显式 Dayboard provider/store ports 和 UoW 已实现；提取等待第二个消费者 |
| Provider usage 和 budget accounting | Dayboard boundary | Platform candidate | 显式 typed ports 和独立 UoW 已实现；提取等待第二个消费者和持久化恢复语义 |
| Reminder delivery/outbox machinery | Dayboard boundary | Split candidate | 显式 Dayboard ports/UoW 已实现；Dayboard 负责到期时间和过期策略，Platform 提取等待第二个消费者 |
| Auth credentials 和 account recovery | Dayboard boundary | Platform candidate | Account Recovery ports/UoW 已明确；提取仍等待具体的第二个消费者或稳定的 identity API |
| Calendar/task domain、repositories 和 services | Dayboard | Dayboard | 永不迁移到 Platform |
| Scheduling prompt、tools、time rules 和 receipts | Dayboard | Dayboard | 永不迁移到 Platform |
| Schedule cards 和 Dayboard web UI | Dayboard | Dayboard | 永不迁移到 Platform |
| Token diagnostics 和跨服务 budgets | Northgate | Northgate | Sidecar；不修改上下文 |

## 复用决策

`agent_platform` 保留为小型 application-lifecycle 包，而不是现有基础设施的替代品。它负责必须跨越进程、设备或运行时
重启而保持的 invariants：可信 tenant scope、原子幂等提交、持久化 Conversation 和 Run 生命周期、带版本的产品
envelopes，以及 interaction CAS。

以下所有权安排是有意为之：

| 能力 | 所有者 | 原因 |
| --- | --- | --- |
| Agent loop、model invocation、LangGraph checkpoints、runtime stream | North | 这些属于运行时关注点，且已有成熟实现 |
| ORM、migrations、row locks、`ON CONFLICT` | Dayboard SQLAlchemy adapter | 当前 PostgreSQL schema 属于一个产品；只有第二个消费者证明其价值后，才提取可选 adapter |
| Platform Conversation/Run/Idempotency/Interaction lifecycle | Agent Application Platform | 这些跨产品 application invariants 不是 checkpoint 或通用 state-machine library 所提供的 |
| Scheduling semantics、local time、cards、reminders | Dayboard | 产品特有的含义不能变成通用的 `Item` model |
| Provider traffic policy 和跨应用 token accounting | Northgate | Gateway policy 必须保持在产品上下文变更之外 |

不要仅为了替代 Platform 而增加另一个 Agent framework、state-machine library 或通用幂等 middleware。没有任何一种
方案能将所需的 tenant-scoped claim、Thread、Run、user message 和 durable event transaction 表达为一个由产品负责的
unit of work。

## 第一个垂直切片：Conversation + Run

Conversation 和 Run 一起迁移，因为它们共享恢复和一致性边界：

```text
submit command
  -> append user message
  -> create Run idempotently
  -> execute product agent through North
  -> persist assistant message and artifacts
  -> finalize Run
  -> recover the same state after refresh or reconnect
```

Platform API 必须使用注入的 ports 来负责：

- transaction/session scope；
- product agent construction 和 execution；
- artifact validation 和 serialization；
- live event projection；
- command dispatch。

Dayboard 保留这些 ports 的 scheduling 实现。Platform 不得导入 Dayboard Pydantic model、SQLAlchemy row、tool name、
prompt 或 presentation type。

## 架构审查发现

第一次提取建立了正确的包方向。本审查将结果记录为当前状态，而不是把已经过时的发现继续当作未解决问题：

| 发现 | 状态 |
| --- | --- |
| Conversation、Run、events 和 idempotency 的显式 Unit of Work | 完成；command submission 和 Run checkpoints 使用共享边界 |
| 与 ORM 无关的 idempotency record、validation、cleanup 和 rollback | 完成；Dayboard application code 不再读取 `IdempotencyKeyRow` |
| 并发 Run-event sequence allocation | 完成；PostgreSQL adapter 通过锁定父 Run 串行化分配 |
| Platform Core/Ports/Application 和 Dayboard Domain dependency checks | 完成 |
| Dayboard Scheduling Unit of Work 和与 ORM 无关的 application services | 完成；schedule writes 和 Reminder Outbox replacement 在 API/Agent 边界原子提交 |
| Dayboard Reminder Unit of Work 和与 ORM 无关的 lifecycle service | 完成；inbox、source projection、claim、expiry、cancellation 和 delivery 使用显式 ports，并由 API/Worker 负责提交 |
| Dayboard Voice Unit of Work 和与 ORM 无关的 lifecycle service | 完成；处理记录在外部 ASR 前提交，terminal transitions 使用第二个事务，提取等待第二个消费者 |
| Dayboard Account Recovery Unit of Work 和与 ORM 无关的 service | 完成；User-first locking 串行化 issue、confirm 和 login，同时 password/token/session 变更原子提交 |
| Dayboard Provider Usage Unit of Work 和与 ORM 无关的 settlement | 完成；owner-scoped 幂等插入返回 typed aggregates，且不能修改已经 terminal 的 Run |
| Outer Platform 和 Run composition | 完成；CommandService 和 Run driver 不再构造 FastAPI、SQLAlchemy、North、Settings 或 runtime adapters，且每个 Worker job 都获得新的 driver |
| 可复用的 PostgreSQL Conversation/Run adapters | 按设计延期；Dayboard 仍是唯一已验证消费者，现在提取共享 schema 或 migration package 会是推测性工作 |
| 带版本的持久化 presentation envelopes | 完成；未带版本的 message metadata 已删除并完成一次迁移 |
| 带版本的持久化 event extension envelopes | 完成；RuntimeJournal extensions 携带 kind、schema version 和经所有者校验的 payload |
| 按预期 state version 原子消费 Interaction | 完成；continuation claim、CAS、Run/event 和 message 一起提交 |
| 明确的 Conversation Thread lifecycle 和 primary-role contracts | 完成；生命周期为 `active | archived`，`is_primary` 独立存在，并拒绝对 archived 对象写入 |
| Clarification authority | 完成；North 为每个 Run 发出 typed `ClarificationRequest`，Dayboard 只映射一次，Platform `PendingInteraction` 是唯一持久化权威 |

剩余发现不需要替换所有权模型。它们定义了迁移更多能力前所需的加固工作。

## 必需的一致性边界

Platform Unit of Work 必须使以下每组操作保持原子性：

```text
command submission
  idempotency claim + Thread resolution + Run + user message + run_created event

Run transition
  compare-and-transition Run + corresponding durable event

interaction resolution
  compare-and-consume interaction version + continuation Run/message creation

Dayboard schedule mutation
  calendar/task CAS write + pending Reminder Outbox cancellation/replacement

Dayboard voice transcription
  commit processing record -> external ASR without a transaction -> commit completed/failed state

Dayboard provider usage
  commit terminal Run -> independently insert immutable usage aggregate -> reconcile budget if created
```

Agent execution 仍位于数据库事务之外。上面的每个持久化检查点都使用短事务；等待 model、tool provider、Redis 或 SSE
consumer 时不得保持事务打开。

Provider Usage 有意不与 Run transaction 保持原子性。独立的 UoW 可防止诊断/记账失败回滚用户可见结果。在结算前发生
硬退出，或 usage commit 与 Redis budget reconciliation 之间发生硬退出时，仍需要 durable outbox 或 repair job 来恢复。

PostgreSQL Run-event sequence allocation 会在计算下一个序号前锁定父 Run，因此并发的生命周期写入者无法取得同一个值。

## 带版本的扩展契约

Platform 可以持久化产品特有的数据，但不解释这些数据：

```text
PresentationEnvelope
  kind
  schema_version
  payload             validated by the product adapter

EventExtensionEnvelope
  kind
  schema_version
  payload             validated by the producing product/runtime adapter

PendingInteraction
  interaction_type
  schema_version
  source_run_id
  payload             validated by the product adapter

ConversationState
  version              compare-and-consume token
  expires_at
  interaction
```

Dayboard 继续负责 `ScheduleResultPart`、scheduling receipts、candidate shapes 和 local-time projection。North 继续负责
临时 `ToolMessage.content` 和 `ToolMessage.artifact` transport。Platform 只负责 durable envelope identity、persistence、
replay 和 interaction lifecycle。
同一个 model context 绝不能同时接收 UTC entity timestamps 和 local-time receipts。

## 一个切片的完成定义

只有满足以下条件，某项能力才算完成提取：

- Dayboard 从 `agent_platform` 导入其 public API；
- 旧的 Dayboard 实现与该切片一起删除；
- migrations 和 data 仍以 PostgreSQL 为权威来源；
- multi-store writes 通过显式 Unit of Work 执行并一起回滚；
- tenant isolation、idempotency、recovery 和 concurrency tests 通过 platform API；
- persisted extension payloads 携带 schema identity/version，并由其所有者校验；
- ORM rows、FastAPI types 和 concrete runtime types 不跨越 Core/application ports；
- platform package 不包含 `dayboard` import，其 public models 不包含 scheduling vocabulary；
- production 只有一条 execution path，不为已移除的内部路径保留 compatibility adapter；
- 只有新路径实际启用后，才更新 `docs/current/`。

## 防护规则

- 不要从共享的 `Item`、任意 JSON domain storage 或 universal tool schema 开始。
- 不要仅根据相似文件名移动模块；应在显式 ports 处分离混合所有权。
- 不要为假想消费者增加 platform APIs。提取已经由 Dayboard 证明的能力，并围绕稳定 invariants 设计它。
- 当 transaction 和 persistence semantics 仍只存在于 Dayboard 时，不要把 Store Protocol 加 forwarding service 视为已完成的可复用能力。
- 不要让 `dict[str, Any]` 变成无版本的 public protocol。Opaque product payloads 需要 platform-owned envelope 和 product-owned validation。
- 不要让数据库事务跨越 model execution、external providers、Redis publication 或 client streaming。
- 不要让包提取在同一个 commit 中改变用户可见行为。
- 保持 Northgate 为观察性组件。它可以报告 Run/token data，但不能选择 prompts、压缩 context 或修改业务写入。

## 里程碑

1. Package skeleton、ADR、ownership map 和 CI dependency check。完成。
2. Trusted identity、Conversation/Run contracts 和 focused contract tests。完成。
3. Run repository ports 和 platform lifecycle service；删除原 Run service。完成。
4. Conversation repository ports 和 platform service；删除原 service path。完成。
5. 修正 dependency documentation，并记录 architecture hardening gaps。完成。
6. 增加 Platform Core 和 Dayboard Domain dependency checks。完成。
7. 增加 Unit of Work 和 platform idempotency contracts；从 command use cases 中删除 ORM records。完成。
8. 增加带版本的 PendingInteraction envelopes 和 atomic continuation submission。完成。
9. 增加带版本的 persisted presentation envelopes 和 typed Dayboard history projection。完成。
10. 将 Thread lifecycle 与 primary role 分离，并拒绝 archived command submission。完成。
11. 在产品特有 replay 需要时，增加带版本的 durable event extension envelopes。完成。
12. 将 generic Run coordination 与 Dayboard Agent execution 和 result projection 分离。完成。
13. 仅在 active Dayboard path 已证明相应契约时，增加可复用的 PostgreSQL/North adapters。
14. 只有在 lifecycle adapters 得到验证后，才考虑 usage accounting 和 notification delivery。
