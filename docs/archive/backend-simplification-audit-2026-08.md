# 后端简化审计

> 这是 2026 年 8 月预发布 abstraction-freeze 清理期间的历史审计。它记录当时工作的具体调用路径，
> 不得用于指导当前实现。当前契约仍位于 `docs/current/`。

## 范围与防护规则

本审计在三条生产路径中查找仅转发参数的代码。它不授权修改事务所有权、持久化状态、并发控制、授权、事件顺序
或 public protocols。

以下 invariants 不属于简化范围：

- Redis command jobs 只携带 `run_id`；Worker 从 PostgreSQL 恢复可信状态。
- PostgreSQL 是 Runs、messages、Interactions、schedules、reminders 和 usage 的权威来源。
- `queued -> running` 会在调用 North 或 model provider 前提交。
- North 或 ASR 执行外部工作时，不会保持数据库事务打开。
- terminal Run state、assistant message、presentation 和可选 Interaction 原子提交。
- terminal PostgreSQL state 会在 terminal browser event 和 stream end marker 之前提交。
- clarification 使用数据库 compare-and-consume state versions。
- schedule writes 使用 `expected_row_version`，并在同一个事务中替换 Reminder state。
- trusted `UserContext`、Run identity 和 operation keys 由 server code 注入。
- application 和 Platform contracts 绝不暴露 SQLAlchemy rows。

## 路径 1：提交 Command

```text
POST /api/command-runs
  -> dayboard.api.routes.create_command_run
  -> FastAPI get_command_service dependency
  -> dayboard.composition.commands.build_command_service
  -> dayboard.app.commands.CommandService.create_or_get_command_run
  -> agent_platform.application.CommandSubmissionService.submit
  -> IdempotencyService + ConversationService + AgentRunService
  -> SqlAlchemyPlatformUnitOfWork stores
  -> one commit
  -> RedisCommandDispatcher.enqueue(run_id)
  -> HTTP 202
```

| 步骤 | 文件和 callable | 决策或 invariant | IO | 纯转发 |
| --- | --- | --- | --- | --- |
| HTTP boundary | `dayboard/api/routes.py:create_command_run` | 映射幂等性和 active-Run 冲突；仅为新创建的 Runs 入队；持久化队列失败 | 通过 dispatcher 使用 Redis | 否 |
| FastAPI dependency | `dayboard/api/dependencies.py:get_command_service` | request-scoped Session wiring | 无 | construction boundary |
| command composition | `dayboard/composition/commands.py:build_command_service` | 选择 Dayboard failure projection 和 clarification adapter | 无 | mostly construction |
| nested composition helper | `dayboard/composition/commands.py:build_command_service_from_platform` | 除相同构造外没有其他职责 | 无 | candidate |
| product command service | `dayboard/app/commands.py:CommandService.create_or_get_command_run` | request identity、Thread title、product logging | 通过 Platform | 否 |
| clarification continuation | `dayboard/app/commands.py:CommandService.create_or_get_clarification_run` | 在原子消费和重新提交前校验所选选项 | 通过 Platform | 否 |
| generic submission | `agent_platform/application/command_submission_service.py:submit` | idempotency claim、active Thread、Interaction CAS、Run/event/message 原子组 | repository ports | 否 |
| Run creation | `agent_platform/application/run_service.py:create_run` | 同时创建 `queued` Run 和 `run_created` event | repository ports | 否 |
| persistence adapter | `dayboard/db/platform_uow.py:SqlAlchemyPlatformUnitOfWork` | 将所有 Platform stores 绑定到一个事务 | PostgreSQL | 否 |

初始决策：

- 保留 FastAPI dependency：它是 transport-to-composition boundary。
- 保留 `CommandService`：它包含 Dayboard policy 和 clarification continuation behavior。
- 保留 `CommandSubmissionService`：它负责 atomic submission use case。
- 如果没有独立调用方需要 `build_command_service_from_platform`，则将其内联或删除。
- 单独审查 `create_command_run` convenience method；生产使用更丰富的结果，而测试当前使用仅返回 UUID 的 wrapper。

## 路径 2：执行 Run

```text
arq execute_command_run(run_id)
  -> open request-independent AsyncSession
  -> build_run_execution_scope
  -> restore Run and trusted UserContext from PostgreSQL
  -> RunExecutionCoordinator.execute
  -> commit queued -> running and run_started
  -> DayboardRunExecutionDriver.execute
  -> North RunExecutor
  -> scheduling tools and runtime event projection
  -> RunExecutionCoordinator complete/fail callback
  -> commit terminal Run + assistant message + presentation/Interaction
  -> publish terminal Redis event
```

| 步骤 | 文件和 callable | 决策或 invariant | IO | 纯转发 |
| --- | --- | --- | --- | --- |
| arq boundary | `dayboard/workers/commands.py:execute_command_run` | 从 Run 恢复 owner identity；队列输入仍只有 `run_id` | PostgreSQL | 否 |
| Run composition | `dayboard/composition/runs.py:build_run_execution_scope` | 组装一个 driver、lock、budget guard、usage settlement、runtime-event UoW factory、North factory 和 stream bridge | 无 | 否 |
| scope method | `dayboard/composition/runs.py:RunExecutionScope.execute` | 无；转发 coordinator、context、Run 和 driver | 无 | candidate |
| lifecycle coordinator | `agent_platform/application/run_execution_coordinator.py:execute` | state machine、provider 前提交、一次 terminal settlement、atomic outcome persistence | 通过 UoW 使用 PostgreSQL | 否 |
| product driver | `dayboard/agent/run_execution.py:DayboardRunExecutionDriver.execute` | budget、North invocation、durable progress、presentation projection、usage 和 terminal publication order | North、PostgreSQL、Redis、provider | 否 |
| runtime | North `RunExecutor` | model/tool execution、compaction、canonical runtime events | provider 和 tools | 否 |

初始决策：

- 不要在 command-submission 清理中简化此路径。
- `RunExecutionScope.execute` 已证明是一个单行转发候选项，但应在 Worker tests 确认直接调用仍清晰后，作为单独的低风险变更删除。
- 保留 `RunExecutionCoordinator`、driver、per-event fresh UoW 以及 terminal callback order。

## 路径 3：重新安排 Calendar Entry

```text
North tool call
  -> dayboard.agent.tools.agent_reschedule_calendar_entry
  -> parse Beijing local model values into trusted timezone-aware datetimes
  -> dayboard.tools.scheduling.reschedule_calendar_entry
  -> operation idempotency + target/CAS validation + duration/conflict policy
  -> SchedulingService.reschedule_calendar_entry
  -> CalendarEntryRepository.reschedule(expected_row_version)
  -> SchedulingService._sync_calendar_reminder
  -> construct compact receipt + complete presentation artifact
  -> serialized tool boundary commit
```

直接的 HTTP 编辑路径在 `SchedulingService.update_calendar_entry_from_ui` 处汇合，然后在 API boundary 提交。

| 步骤 | 文件和 callable | 决策或 invariant | IO | 纯转发 |
| --- | --- | --- | --- | --- |
| model boundary | `dayboard/agent/tools.py:agent_reschedule_calendar_entry` | model schema validation、Beijing-local conversion、trusted Run operation key、receipt/artifact split | 无 | 否 |
| serialized tool use case | `dayboard/tools/scheduling.py:reschedule_calendar_entry` | idempotent replay、target validation、duration semantics、conflict reporting、optimistic-lock failure | 通过 application service | 否 |
| scheduling service | `dayboard/app/scheduling.py:SchedulingService.reschedule_calendar_entry` | schedule mutation 和 Reminder synchronization 仍是一个 use case | repository ports | 否 |
| scheduling UoW | `dayboard/db/scheduling_uow.py:SqlAlchemySchedulingUnitOfWork` | 将 Calendar、Task 和 Reminder stores 绑定到一个事务 | PostgreSQL | 否 |
| repository | `dayboard/db/repositories.py:CalendarEntryRepository.reschedule` | 在一次 SQL update 中完成 user scope 和 `row_version` CAS | PostgreSQL | 否 |
| commit owner | `dayboard/agent/tools.py:serialize_tool` | 仅在 receipt 和 artifact 构造完成后提交；任何失败都回滚 | PostgreSQL | 否 |

初始决策：不要从此路径移除任何层。它的长度体现的是彼此不同的 protocol、business-policy、transaction、persistence
和 presentation responsibilities，而不是重复的参数转发。

## Composition 审计队列

按生命周期审查 scopes，而不是强制执行数值上的 scope 限制：

| Scope | 调用方需要 wrapper 的原因 | 初始动作 |
| --- | --- | --- |
| `PlatformServiceScope` | 多个 services 共享一个 Platform transaction | 保留 |
| `RunExecutionScope` | 将 Platform state lookup 与一个 Run driver 组合 | 仅审查 forwarding method |
| `SchedulingServiceScope` | API/tool callers 需要 service/query 以及显式 commit boundary | 保留 |
| `ReminderServiceScope` | API/Worker callers 显式提交 reminder transaction | 保留 |
| `AccountRecoveryServiceScope` | API 提交 credential/token/session atomic groups | 保留 |
| `VoiceServiceScope` | 调用方只使用 `transcriptions`；service 自身控制多阶段事务 | simplification candidate |

不要在本次清理中增加 `AppContainer`。当前显式的 Session-based builders 规模小且易于搜索；只有已经证明存在生命周期或构造
问题时，才有理由引入 process container。

## 接口审计规则

仅凭实现数量不足以证明可以删除 Protocol。即使只有一个 production adapter，也要保留 storage、provider、execution、
clock 和 deterministic-test boundaries。只有在接口仅有一个实现、一个调用方、没有有用的 fake，且不能保护 application
code 免受 infrastructure 或 external protocol 影响时，才删除它。

## 完成标准

- command submission 不再经过冗余的嵌套 composition helper；
- 每个保留的 scope 都在本审计中有明确的 transaction 或 lifecycle 理由；
- 不修改 public API、database schema、event order 或 transaction boundary；
- targeted command 和 worker checks 通过；
- 决策完成后，本审计保留在 `docs/archive/` 下；
- 接下来的三个有意义变更优先改善产品行为或体验，而不是架构。

## 已完成的决策

- `build_command_service_from_platform` 已删除；`build_command_service` 现在直接执行显式构造。
- `VoiceServiceScope` 已删除；Voice builder 现在直接返回负责事务的 `VoiceTranscriptionService`。
- 未使用的 `build_command_submission_service` helper 已删除。
- `RunExecutionScope.execute` 仍然保留，因为它是 Worker 和 Run execution tests 使用的内聚 public operation；暴露其 coordinator/driver 组合会增加耦合。
- Platform、Scheduling、Reminder 和 Account Recovery scopes 仍然保留，因为调用方将它们共享的 Unit of Work 用作显式 transaction boundary。
- Protocol 审计没有删除任何 ports。低引用协议属于 structural storage、provider、runtime 或 deterministic-test boundaries；production adapters 有意不必名义上继承它们。
- 没有增加共享的 SQLAlchemy UoW base。在 abstraction freeze 期间，小规模重复的 `commit`/`rollback` methods 比新增 inheritance layer 成本更低。
- 没有引入 `AppContainer`、service locator、top-level backend layer、Platform capability 或 public protocol。
