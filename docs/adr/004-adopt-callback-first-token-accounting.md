# ADR-004 采用 callback 优先的 Token 计量

## 状态

已接受

## 背景

Dayboard 需要准确的 provider 用量，以支持成本可见性、租户预算和未来计费。模型用量是运行时事实，
但租户归属、定价、持久化和预算策略属于产品关注点。

仅从最终 LangGraph 状态读取用量是不完整的，因为中间模型调用可能选择工具、执行澄清，或在生成最终
消息前失败。在 agent middleware 中进行基础计数也会混淆观测与执行状态，并可能使计量依赖于消息重写。

DeerFlow 使用基于 callback 的 RunJournal 作为权威观测器，从 worker finalization path 持久化 Run
用量，并将 middleware 保留给步骤归属和主动预算执行。Dayboard 的运行时更简单且没有 subagents，
但应遵循相同的边界。

## 决策

采用以下所有权模型：

```text
provider model call
  -> LangChain callback
  -> north.RuntimeJournal emits model.completed
  -> north normalizes provider usage
  -> north.RuntimeUsageAccumulator deduplicates by call_id
  -> Dayboard finalizes the Run
  -> Dayboard persists one provider usage summary for the Run
  -> Dayboard applies tenant budgets, pricing, and reconciliation
```

North 负责：

- 通过 callbacks 观测每次模型调用；
- 将常见 provider 字段规范化为 `input_tokens`、`output_tokens` 和 `total_tokens`；
- 在 provider 未提供 `total_tokens` 时推导该值；
- 按模型调用 ID 对重复的 callback 交付去重；
- 暴露与产品无关的用量事件和内存聚合结果。

Dayboard 负责：

- 将用量关联到租户、用户、Run、provider 和已配置模型；
- 持久化 PostgreSQL 用量记录；
- 为每个 Run 提供数据库级 exactly-once 保证；
- 负责准入预算、计划限制、定价以及实际值与估算值的对账；
- 决定哪些用量元数据可以安全地暴露在产品可观测性中。

基础 Token 计量不是 agent middleware。callback 在不改变 agent 状态或控制流的情况下观测执行。只有当
某项策略必须参与执行时，才引入 middleware，例如在 agent 接近每个 Run 的限制时发出警告、在达到硬
限制后阻止新的工具调用，或将 subagent 用量归属回父步骤。

## 当前实现

North 发出规范化用量，`RuntimeUsageAccumulator` 按 `call_id` 聚合成功的 `model.completed` callbacks。
Dayboard 使用独立的数据库 session 消费该 accumulator，并从 Run 的 `finally` path 结算一条
`provider_usage_records` 记录。因此，只要模型完成事件报告了用量，成功、澄清、失败、中断和取消都会
共用同一条结算路径。

数据库对 `(tenant_id, run_id)` 强制唯一性。结算会插入不可变的聚合记录，并将冲突视为 Run 已经结算，
因此重试不会创建重复记录，也不会再次扣除预算。结算失败会单独记录日志，不会替换 Run 的产品结果。

Dayboard 还会执行保守的调用前预算准入检查。首次成功结算会在同一固定窗口中计入
`max(actual_tokens - estimated_tokens, 0)`。实际值较低时不会退款，因为 Run 可能在准入窗口过期后
才结算；否则负向调整可能破坏下一个窗口。PostgreSQL 记录仍是实际用量这一事实的权威来源。

## 必要的后续工作

为独立结算耗尽数据库重试机会这一罕见情况增加运维恢复路径；结构化结算失败日志是当前的检测机制。
如果商业上确实需要精确退款，应使用持久化预留模型替代固定窗口预留，而不是应用负向计数器调整。

按模型划分的桶、缓存读取 Token、lead/middleware/subagent 归属、运行中快照以及 token-budget
middleware 均推迟到产品使用多个模型、subagents，或需要主动成本控制的长时间运行任务之后再实现。

## 后果

计量来源仍可跨产品复用，同时无需让 North 感知租户、数据库、价格或计划。Dayboard 可以在保留相同
运行时用量事实的同时独立演进计费能力。

简短的调度命令避免了 DeerFlow 完整的归属和执行复杂性。剩余的权衡是：结算期间发生数据库故障时需要
运维恢复；该架构将其视为计量可靠性工作，而不是新的 middleware 功能。
