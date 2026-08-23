# ADR-009 保持 Platform 与 North 独立

## 状态

已接受

## 背景

ADR-008 引入了 `agent_platform`，用于承载不属于调度产品或 Agent 运行时的应用生命周期能力。它最初的依赖图描述了一条严格链路：
`Dayboard -> agent_platform -> North`.

已实现的 Run 边界证明这条链接既不必要又有害。North 已经负责 Agent 循环、模型调用、LangGraph 检查点和运行时流。Agent Platform 负责持久化的租户范围 Conversation、Run、幂等性、封装和交互生命周期。Platform 不需要导入 North 来表达这些规则；Dayboard 提供 `RunExecutionDriver` 连接两个包。

为了保留视觉上的三层栈而强迫 Platform 导入 North，会在应用代码中重复运行时概念，并使每个未来消费者都必须采用 North，即使其运行时需求不同。

## 决策

保持 North 和 Agent Platform 为彼此独立的底层依赖：

```text
Dayboard ------> agent_platform
   |
   +-----------> North

future product -> agent_platform
future product -> its chosen runtime
```

Dayboard 的 composition root 创建产品所有的适配器，实现 Platform 的 `RunExecutionDriver` port。North 和 Platform 不互相导入。North 图状态是临时运行时状态；Platform 基于 PostgreSQL 的 Conversation 和 `PendingInteraction` 状态是持久化的应用权威来源。

只有当第二个产品证明存在稳定且与产品无关的集成契约时，才允许添加可选的 North 适配器包。它必须向内依赖 Platform ports，且不得改变无框架的 Core 或 Application 包。

## 后果

- Platform 保持精简，目前只依赖 Pydantic。
- North 可以继续演进运行时、检查点、流和压缩 API，而不与租户持久化或产品语义耦合。
- 产品拥有明确的桥接，并可以选择其他运行时，而不必替换其持久化 Conversation/Run 生命周期。
- 在第二个产品证明存在共享持久化 schema 和事务契约之前，PostgreSQL 适配器仍归 Dayboard 所有。
- 澄清桥接必须将 North 的临时信号收敛为一个 Platform 结果；不得创建第二个持久化交互权威来源。
