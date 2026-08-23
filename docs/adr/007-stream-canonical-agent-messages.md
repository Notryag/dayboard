# ADR-007 流式规范 Agent 消息

## 状态

已接受

## 背景

Dayboard 当前从 PostgreSQL 追踪 `agent_run_events`，并将这些可观测性记录用作实时 UI 协议。这些事件描述生命周期和进度，但丢弃了规范的 AI 消息和工具消息。Run 完成后，Web 客户端查询 `/api/schedule-items/by-runs`，再根据 `created_by_run_id` 与该 Run 匹配的业务行推断聊天卡片。

这种设计有四个问题：

- 工具结果到达时无法立即渲染；
- 只有当 Run 到达终止状态时，模型输出才会被交付；
- 无法可靠地根据 `created_by_run_id` 重建已更新和已取消的对象；
- 可观测性事件、产品呈现和业务持久化被混为一谈。

DeerFlow 使用了不同的边界。图会发出规范的 `values`、`messages` 和 `custom` 分块。流桥将这些分块传输给客户端，前端再把 AI 消息分块和 ToolMessages 归约为 UI。其持久化日志属于可观测性范畴，而不是主要的呈现协议。

Dayboard 仍在开发中。目前没有需要保留的已发布客户端契约，因此旧的 `/api/schedule-items/by-runs` 推断路径将被移除，而不是作为兼容路径保留。

## 决策

采用规范消息流，并明确 North 与 Dayboard 的所有权。

### North 负责

- 唯一的生产 `agent.astream` 循环，由异步 Run executor 实现；
- Run 执行顺序：元数据、规范分块、生命周期收尾、错误和结束；
- 将图流模式规范化为 `RuntimeStreamEvent`；
- 保留序列化的消息数据、流模式、命名空间、消息 ID 和工具调用 ID；
- 带有重放游标、心跳和结束哨兵的异步 `StreamBridge` 契约；
- 与产品无关的内存版和 Redis Stream bridge 实现；
- 由 Run executor 直接向 StreamBridge 发布规范分块；
- 流结束后向调用方返回最新的 `values` 状态。

North 不得了解任务、日历条目、租户、FastAPI、Redis 部署或 Dayboard 呈现 schema。

### Dayboard 负责

- 选择产品使用的 North 流模式；
- 通过严格的逐工具 allowlist 投影规范 ToolMessages；
- 仅从根图命名空间呈现调度 ToolMessages，除非未来的 ADR 明确认可某个具名子图；
- 将安全的调度工具结果映射为类型化的对话部分；
- 租户和所有者授权；
- PostgreSQL 业务写入和对话历史；
- 选择并配置 North 基于 Redis 的实时扇出；
- 在 North 发布结束哨兵前，持久化 Dayboard Run 状态、对话消息和产品状态的生命周期钩子；
- SSE 成帧、重连游标、心跳和终止 Run 语义；
- 前端归约器以及文本和调度部分的渲染。

实时路径为：

```text
North async RunExecutor
  -> agent.astream(values, messages)
  -> North StreamBridge.publish(canonical mode)
  -> Dayboard safe message projector
  -> Dayboard SSE join endpoint
  -> web Run reducer
  -> assistant text and schedule cards
```

恢复路径为：

```text
safe projected tool parts collected during Run
  -> assistant conversation message metadata
  -> PostgreSQL conversation history
  -> web message renderer
```

工具写入必须先提交，之后其 ToolMessage 才能被视为成功的产品结果。ToolMessage 是呈现数据，不是创建或修改调度对象的权威来源。

## 流协议

North 发出与产品无关的事件：

```text
RuntimeStreamEvent:
  mode: values | messages | custom
  namespace: tuple[str, ...]
  data: JSON-compatible serialized graph chunk
```

传输协议为：

```text
StreamBridge:
  publish(run_id, event, data, namespace)
  publish_end(run_id)
  subscribe(run_id, last_event_id, heartbeat_interval)
  cleanup(run_id)
```

Dayboard 只向浏览器暴露经过投影的事件：

```text
assistant_text_delta:
  message_id
  delta

schedule_item_result:
  tool_call_id
  operation
  item: { kind: calendar | task, value: safe product snapshot }

run_completed | clarification_requested | run_failed | run_cancelled
```

浏览器绝不解析自然语言模型内容来发现产品对象。它通过 `tool_call_id` 对工具结果建立索引，并对重传的流条目去重。最终的助手文本与调度结果卡片是彼此独立的消息。

## 持久化与重连

- PostgreSQL 仍是 Runs、对话、任务和日历条目的事实来源。
- Redis Streams 提供跨进程实时扇出和有界重放，而不是产品事实来源。
- SSE join endpoint 使用标准的 `Last-Event-ID` 游标，并通过 Bridge 恢复传输。
- 如果游标早于 Redis 的保留范围，Bridge 会在重放最早的保留事件前发出明确的重放缺口信号；该缺口绝不会被视为完整重放。
- 实时历史过期或 Run 终止后，客户端从 PostgreSQL 重新加载规范对话历史。
- 助手对话消息元数据存储安全的投影部分，因此历史卡片不需要通过 Run ID 查询业务对象。
- RuntimeJournal 事件仍保留在 `agent_run_events` 中，用于审计、进度、用量和诊断。它们不会被解析为规范消息。

## 移除内容

本次迁移将移除：

- `GET /api/schedule-items/by-runs`；
- `RunScheduleItemGroup` 和前端批量获取 effect；
- 通用进度解析器中的 `calendar_entry_created`、`task_item_created` 等产品事件标签；
- 认为 `tool_call_completed` 包含足够数据来渲染产品结果的假设。

## 禁止的捷径

以下做法即使能减少实现工作量，也属于架构违规：

- Dayboard 服务直接调用 `agent.astream`；
- 使用诸如 `stream_agent_once` 的 helper，通过 callback 返回流式分块，同时绕过 RunExecutor 和 StreamBridge；
- 使用 stream sink callback 作为主要实时传输方式；
- 并行维护同步和异步生产 Run worker；
- 在 Dayboard 生命周期钩子持久化完成 Run 之前发布结束哨兵；
- 轮询 `agent_run_events`，以此替代实时 StreamBridge；
- 为尚未发布的开发契约增加兼容路径，而不是将其移除。

代码审查和测试必须强制使用唯一的生产执行路径：

```text
Dayboard Worker -> North RunExecutor -> North StreamBridge -> Dayboard SSE
```

## 实现映射

North 实现：

- `north/runtime/worker.py`：`RunExecutor`、生命周期顺序、规范模式发布；
- `north/runtime/stream_bridge/base.py`：异步传输协议和哨兵；
- `north/runtime/stream_bridge/memory.py`：供 SDK 使用和测试使用的进程内重放；
- `north/runtime/stream_bridge/redis.py`：跨进程 Redis Streams 传输；
- `north/runtime/service.py`：使用同一 executor 的异步 Run 编排；
- `north/client.py`：基于异步 runtime 的同步 SDK 适配器，而不是第二个 worker。

Dayboard 实现：

- `dayboard/workers/commands.py`：为 Worker 构造 North Redis bridge；
- `dayboard/app/commands.py`：提供产品生命周期钩子并持久化安全部分；
- `dayboard/agent/presentation.py`：allowlist 规范消息投影；
- `dayboard/main.py`：为 API 进程构造同一个 North Redis bridge；
- `dayboard/api/routes.py`：授权、Bridge 订阅、投影和 SSE 成帧；
- `apps/web/src/app/page.tsx`：Run 事件归约和浏览器重连行为；
- `apps/web/src/features/chat/ChatMessageList.tsx`：文本和调度部分渲染。

## 后果

调度卡片和模型文本可以增量渲染，重连拥有明确的协议，历史聊天渲染也不再依赖针对可变业务行的反向查询。

这项实现比轮询一张 PostgreSQL 表更加复杂。它需要 Redis stream adapter、安全投影层、持久化的对话部分和前端归约器。这些边界是有意设置的，因为它们让实时传输、可观测性、历史和业务状态彼此分离。
