# ADR-011 使用按调用准确计量的 Agent 活动

## 状态

已接受

## 背景

Dayboard 已经持久化 North 模型和工具生命周期事件，并将安全的工具进度流式传输到浏览器。当前 Web 客户端将每个进度事件追加到 ticker，因此一次工具调用可能显示为独立的“开始”和“完成”消息。Run 结束后，它还会立即丢弃这些活动。

Lexora 是第二个 North 和 Agent Platform 消费者。它的法律工作流增加了 subagent，并暴露出相同的关联问题：按工具名称分组会隐藏独立搜索，而将每个事件分组会产生重复行。DeerFlow 通过稳定的工具调用和任务身份解决这一问题，并将产品呈现与运行时数据分离。

## 决策

North 仍是与产品无关的运行时事实来源：

```text
model invocation      call_id
tool invocation       call_id
subagent invocation   task_id
subagent child work   task_id + its own call_id
```

North 会将 `task_id` 传播到 subagent 内执行的模型和工具事件上。它不负责中文标签、持久化、脱敏或视觉组件。

Dayboard 将继续在 `dayboard.agent.observability` 中投影 North 事件。该投影只发布 UI 所需的允许字段：稳定身份、技术操作名称、安全的产品摘要、终止状态和时长。原始模型输出、推理、未限制的输入、工具结果和提供商错误仍然排除在外。

浏览器会按 `call_id` 合并一次调用的开始事件和终止事件。对同一工具的独立调用仍保持为不同的行。活动视图在执行期间和失败时展开，成功回答后折叠，并且可以重新打开。Dayboard 当前没有产品 subagent，但其事件解析器会保留通用的 `task_id` 契约，使未来的 specialist 不需要第二套协议。

Lexora 使用相同的关联规则，同时负责法律 Agent 名称和检索摘要。两个应用不共享 React 组件或产品标签。

## 后果

- 显示的工具状态对应真实调用，而不是事件到达顺序。
- 重复搜索和操作仍可独立观测。
- 产品专用脱敏逻辑保留在各产品工具 schema 附近。
- UI 可以总结模型调用，但不得仅根据时间自行编造 specialist 阶段。
- 现有事件行和较旧的 SSE 载荷通过有界回退仍可读取。
- Dayboard 中按消息划分的历史活动留待后续切片；本决策首先修复活动 Run 和最近完成 Run 的体验，不改变消息持久化。
