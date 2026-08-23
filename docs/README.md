# Dayboard 文档

## 从这里开始

只阅读任务所需的内容：

1. [PROJECT_STATE.md](./PROJECT_STATE.md)：版本、已完成工作、下一里程碑、已知问题和发布检查。
2. [current/README.md](./current/README.md)：已实现的产品事实和契约。
3. [engineering-guidelines.md](./engineering-guidelines.md)：添加代码前必读。
4. 下面与任务对应的 current 文档、指南或运行手册。

## 文档模型

每项事实由一个文档负责。其他文档应链接到它，而不是复制内容。

| 位置 | 负责内容 | 不得包含 |
| --- | --- | --- |
| [`current/`](./current/README.md) | 已实现架构与规范的事实来源。 | 计划或实现过程记录。 |
| [`adr/`](./adr/README.md) | 高成本决策及其历史依据。 | 持续改写的当前状态摘要。 |
| [`guides/`](./guides/) | 面向任务的开发、验收和 Eval 流程。 | 重复的架构事实。 |
| [`operations/`](./operations/) | 部署、恢复和生产诊断。 | 产品路线图。 |
| [`plans/`](./plans/) | 仅未完成的进行中工作。 | 作为历史保留的已完成清单。 |
| [`records/`](./records/) | 测量、实验和只追加的证据。 | 规范性的当前行为。 |
| [`archive/`](./archive/README.md) | 已完成或已取代的计划与审计。 | 实现指导。 |

`docs/` 是版本化的事实来源。不要为架构或 Agent 规范创建单独的 Wiki 副本。生成的文档站点可以使用这些文件作为来源。

## 当前规范事实

- [当前架构](./current/architecture.md)：系统和所有权边界。
- [模块图](./current/module-map.md)：代码位置、依赖、事务和不变量映射。
- [产品模型](./current/product-model.md)：调度/任务语义和产品范围。
- [身份模型](./current/identity-model.md)：已认证的所有权和隔离。
- [Run 生命周期](./current/run-lifecycle.md)：Run 状态、流、SSE、持久化和恢复。
- [时间协议](./current/time-protocol.md)：模型本地时间、UTC 存储、工件和 CAS。
- [Agent 契约](./current/agent/README.md)：行为、工具、上下文/记忆和评估。
- [UI 设计](./current/ui-design.md)：当前的视觉和交互规则。
- [API 错误](./current/api-errors.md)：稳定的 HTTP 错误封装。

## 指南与运维

- [工程指南](./engineering-guidelines.md)：编码、分层、测试和安全。
- [Agent 验收](./guides/agent-acceptance.md)：已部署实时模型的定向检查。
- [Agent Eval](./guides/agent-eval.md)：版本化的定量调度基准。
- [部署](./operations/deploy.md)：生产构建、发布、回滚和健康检查。
- [PostgreSQL 备份](./operations/postgres-backup.md)：备份和恢复流程。
- [Token 诊断](./operations/token-usage-diagnostics.md)：提供商用量和缓存诊断。
- [语音诊断](./operations/voice-latency-diagnostics.md)：录音延迟阶段测量。

## 计划、记录、决策与历史

- [当前路线图](./plans/roadmap.md)：未完成的 token、gateway、Eval 和通知工作。
- [Token 优化记录](./records/agent-token-optimization-history.md)：只追加的生产测量记录。
- [ADR](./adr/README.md)：架构决策及其依据。
- [归档](./archive/README.md)：过期计划和审计；绝不能作为当前指导。

## 任务路由

Agent、工具、提示词、上下文或 Eval 变更：

- 从 [current/agent/README.md](./current/agent/README.md) 开始；
- 只有相关边界受影响时才添加 Run 生命周期或时间协议；
- 执行付费或已部署检查前阅读对应指南。

后端或数据库变更：

- 当前架构、模块图、产品模型和工程指南；
- 仅在相关时阅读身份、时间、API 错误或备份契约。

前端变更：

- 当前架构、产品模型、UI 设计和工程指南。

部署或生产诊断：

- 对应的运维运行手册；
- 发布前阅读 `PROJECT_STATE.md` 发布检查清单。
