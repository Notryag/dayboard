# ADR-003 分离会话与检查点持久化

## 状态

于 2026-07-10 接受。

## 背景

North 接受 LangGraph 的 `thread_id`，但原有回退逻辑会为每次 Agent 构建创建内存 saver。Dayboard 还将 `run.id` 作为 `thread_id` 传入，因此每个命令都被隔离，尽管 `agent_runs` 已经记录了独立的 Thread 标识符。

DeerFlow 将 Thread 元数据、LangGraph 检查点、Run 日志和 Thread 范围文件分离。其 checkpointer 支持内存、SQLite 和 PostgreSQL；摘要功能将运行时消息压缩为 `summary_text`，而 Run 历史保留产品 UI 必须继续显示的消息。

## 决策

- Dayboard 负责产品会话、租户授权、可见消息、保留策略、结构化待处理操作以及向用户公开的摘要。
- North 负责可复用的 checkpointer 构建和运行时状态连续性。
- `conversation_thread.id` 是可运行的 `thread_id`；`agent_run.id` 标识一次执行。
- 检查点是运行时内部数据，不是 Dayboard 的聊天历史 API。
- 只有宿主 hook 能够归档消息后，上下文压缩才可以从 LangGraph 状态移除消息。它绝不能删除产品的可见消息历史。
- Worker 负责异步 checkpointer 生命周期，并将一个共享 saver 注入所有 Agent。

## 推进步骤

1. 增加 North 的可配置异步 checkpointer 提供商，并使用真实 Run 的 `thread_id`。
2. 增加 Dayboard 会话/Thread 和消息持久化，以及 Thread 范围的 Run API。
3. 在 Worker 中启用 North 的 PostgreSQL saver。
4. 增加可配置摘要和压缩前归档 hook。
5. 根据持久化产品状态、摘要和最近完整轮次组装模型上下文。

第一步推进期间，Worker 会继续使用内存后端，直到 Dayboard 暴露稳定的产品 Thread。这样可以避免积累当前还没有客户端能够恢复的永久检查点。

## 结构化待处理状态

Dayboard 将澄清状态与消息和检查点分开持久化。该状态只存储待处理操作、面向用户的问题、有界结构化数据、版本和过期时间。成功的后续操作会清除它；失败或取消的后续操作会保留它以便重试。该状态属于产品数据，即使 North 压缩运行时消息，也仍然可用。
