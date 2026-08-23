# Agent 上下文与记忆规范

状态：当前规范（规范版本）
最后验证：2026-08-23

## 目标

定义 Dayboard 如何组装、压缩和投影 Agent 上下文，同时不削弱 UI 恢复、乐观锁、跨轮次调度语义或运行时可观测性。

## 所有权

```text
Dayboard   调度语义、紧凑回执、呈现工件、UI 历史
North      通用消息生命周期、流传输、原子保留、压缩时机
Northgate  提供商 token 测量、缓存诊断和预算
```

North 不得理解 Dayboard 实体字段。Northgate 不得变更 Agent 上下文，也不得从提供商流量推断压缩调用。

## 当前压缩策略

当前启用的 Run 感知设置为：

```env
DAYBOARD_SUMMARIZATION_NORMAL_TRIGGER_TOKENS=6000
DAYBOARD_SUMMARIZATION_EMERGENCY_TRIGGER_TOKENS=12000
DAYBOARD_SUMMARIZATION_MESSAGE_CEILING=60
DAYBOARD_SUMMARIZATION_TARGET_TOKENS=2000
DAYBOARD_SUMMARIZATION_MIN_GROWTH_TOKENS=3000
DAYBOARD_SUMMARIZATION_MAX_EMERGENCY_COMPACTIONS=2
```

摘要和模型生命周期事件仍是持久化审计和用量记录，但 Dayboard 不会将它们发布到面向用户的 SSE 流。产品显示 processing、searching、saving 和 failure 等生命周期和工具级状态。

## 模型结果与呈现工件

调度工具使用 LangChain 的 `content_and_artifact` 响应契约：

```text
ToolMessage.content   compact JSON ModelResult visible to the model
ToolMessage.artifact  full validated PresentationPart for the product projection
```

紧凑结果只包含后续推理所需的字段：

- 稳定的结果类型；
- 实体 ID 和简洁标题；
- 时间类型以及计划日期/开始/结束值；
- 用于乐观锁的状态和 `row_version`；
- 仅在相关时提供提醒或冲突摘要。

它省略 `created_at`、可信固定时区、空集合和提醒、Run 审计 ID、重复 ID 以及无关冲突字段。

工件携带完整且安全的 `ScheduleDisplayItem` 快照。产品事务提交后，Dayboard 校验工件，发布类型化调度结果，并将其持久化到助手会话元数据中。PostgreSQL 会话元数据是刷新恢复的权威来源。LangGraph 检查点工件是传输副本，在持久化投影后可以于后续压缩中移除；它不是产品历史存储。

必经路径：

```text
ToolMessage artifact
  -> LangGraph state
  -> North canonical message stream
  -> Redis StreamBridge
  -> Dayboard safe projector
  -> browser SSE reducer
  -> assistant conversation metadata
  -> refresh recovery
```

North 传输 JSON 兼容工件但不解释它们。Dayboard 在投影边界拒绝格式错误或不安全的工件。

## Run 感知压缩

North 应用两个阈值：

```text
Run 开始：history > 6000 tokens -> 一次普通压缩
Run 执行：完整模型可见上下文 > 12000 tokens -> 紧急压缩
保留历史目标：约 2000 tokens
再次压缩前的最小增长：3000 tokens
每个 Run 的紧急压缩次数：上限为 2
```

Run 感知计数器位于调用状态/运行时上下文中，而不是可变的中间件实例字段中。每个 Run 最多进行一次普通压缩。保留策略以 token 为目标，绝不将 AI 消息的工具调用批次与对应的 ToolMessage 分开。ToolMessage 内容已经是宿主定义的紧凑回执；North 不转换 Dayboard 业务字段。旧呈现工件只有在宿主完成持久化投影后才可以丢弃。

`history_tokens` 表示序列化的消息历史。`context_tokens` 表示模型可见的系统提示词、绑定工具 schema 和消息历史。代码和遥测不得混用这两个名称。

## 跨轮次锚点

after、then、next、`之后`、`然后`、`接着` 和 `完成 X 后` 等表达式可以将新日历条目锚定到已有的定时条目。Dayboard 要求先搜索，然后通过带锚点的输入创建：

```text
anchor_entry_id
expected_anchor_row_version
```

直接 `local_start` 和锚点模式互斥。在一个事务中，调度服务锁定并校验锚点，拒绝已取消、全天、缺少结束时间或已过期的条目，根据当前锚点 `end_time` 推导新的开始时间，检查冲突并创建条目。零个匹配项不写入；多个匹配项使用 `ask_clarification`。

示例：

```text
明天上午去跳舞
跳完舞蹈去唱歌

search_calendar_entries(title_query="跳舞", ...)
create_calendar_entry(
  title="唱歌",
  anchor_entry_id=<selected id>,
  expected_anchor_row_version=<selected row_version>,
)
```

## 验证

- 紧凑工具结果 fixture 保持在明确的 token 预算内；
- 保留的 ToolMessage 历史至少比基线小 50%；
- 普通 Run 不会压缩两次；
- 紧急压缩保持有界并保留原子工具批次；
- 工件在实时显示和刷新后恢复时保持一致；
- 紧凑搜索结果保留变更所需的 ID 和 `row_version`；
- 先跳舞再唱歌的流程会在权威的跳舞结束时间创建唱歌条目；
- 用户 SSE 绝不包含摘要或模型生命周期事件；
- 按 `run_id` 进行的 Northgate 对比报告输入、缓存和总 token，而 North/Dayboard 事件报告压缩次数。

对应的实现和确定性检查位于
[`dayboard/config.py`](../../../apps/api/src/dayboard/config.py),
[`dayboard/agent/middleware.py`](../../../apps/api/src/dayboard/agent/middleware.py)、
[`test_agent_middleware.py`](../../../apps/api/tests/test_agent_middleware.py) 和
[`test_scheduling_tools.py`](../../../apps/api/tests/test_scheduling_tools.py)。生产 token 测量属于[优化记录](../../records/agent-token-optimization-history.md)，不属于当前状态契约。
