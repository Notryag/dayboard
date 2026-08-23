# ADR-002 采用 DeerFlow 运行时可观测性边界

## 状态

已接受

通过 tail PostgreSQL 实现实时交付的临时决策已被 ADR-007 取代。RuntimeJournal 可观测性边界
仍然有效。

## 背景

Dayboard 最初直接从调度工具发出进度文本。这样虽然能让首次 SSE 体验可见，但无法解释模型调用、
关联工具输入与输出、报告延迟，也无法在不增加更多产品专用埋点的情况下扩展到新工具。

DeerFlow 将两个相关关注点分开：

1. LangGraph stream modes 被桥接到按 Run 划分的实时流，用于即时交付、心跳和重连。
2. 基于 callback 的 RunJournal 将模型、工具、消息、用量和生命周期数据规范化到持久化事件存储中，
   以供历史记录和审计使用。

它的前端使用 tool call IDs，从结构化的 AI 消息和 Tool 消息中重建推理与工具步骤。DeerFlow 还将
Gateway、持久化和 UI 保留在其可复用 agent harness 之外。

Dayboard 需要相同的边界，但不需要 DeerFlow 完整的 Gateway、sandbox、subagent、artifact 或
administration surface。

## 决策

采用以下设计：

- `north.RuntimeJournal` 将 LangChain callbacks 转换为与产品无关的运行时事件。
- `north.RuntimeEventSink` 是产品所需的唯一集成边界。
- 模型和工具事件使用 call IDs，以便关联开始事件和终态结果。
- `north` 不选择持久化方式、租户策略、SSE 端点或面向用户的文本。
- Dayboard 通过 allowlist 筛选运行时事件，将其持久化到 PostgreSQL，并通过现有的 Run SSE 端点
  提供服务。
- 当冲突检查等产品事件描述了通用模型/工具 callbacks 无法表达的行为时，可以继续显式记录这些事件。
- 即使 Dayboard 的首个实现对两者都通过 tail PostgreSQL 来实现，实时交付和持久化历史仍是两个独立概念。

初始规范化事件包括：

```text
model.started
model.completed
model.error
tool.started
tool.completed
tool.error
```

Dayboard 将这些映射为面向产品的事件，例如 `agent_model_started` 和 `tool_call_started`。

## 安全与呈现

- 永远不要持久化或展示系统提示词、凭据、数据库 URL、隐藏的租户上下文或不受限制的工具输出。
- 工具输入在持久化前按工具名称通过 allowlist 筛选。
- 模型响应正文和 provider 原始推理不会持久化到 Dayboard 进度事件中。
- 未来只有通过明确且单独审查的呈现策略，才能支持 provider 提供的推理。Dayboard 不得为了可观测性
  合成或请求隐藏的 chain of thought。
- 面向用户的进度描述可验证的状态和操作，而不是不可验证的内部思考。

## 后果

Dayboard 无需修改每个工具，就能显示正在运行的操作、安全参数、结果、延迟和模型用量。断开连接或
进程重启后，历史事件仍可重放。

每引入一个新工具，都必须维护产品适配器。未知工具在被显式加入 allowlist 前，只会获得通用文本，
不会获得输入字段。ADR-007 增加了用于实时规范消息的 Redis Stream，而 PostgreSQL 仍是持久化事实来源。
