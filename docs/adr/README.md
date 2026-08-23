# 架构决策记录

将需要付出较高代价才能逆转，或会影响 Dayboard 多个部分的决策记录在此目录。

建议格式：

```text
# ADR-000 标题

## 状态

提议 | 已接受 | 已取代

## 背景

是什么问题迫使我们做出该决策？

## 决策

我们选择什么？

## 后果

什么会变得更容易，什么会变得更困难，以及这意味着哪些后续工作？
```

当以下领域出现新的、逆转代价较高的决策时，创建新的 ADR：

- UI 框架或组件系统替换
- 数据库或租户隔离策略
- Dayboard/North 所有权边界
- Worker 或队列替换
- 身份认证或外部通知提供商边界

## 已接受的决策

- [ADR-001：采用 DeerFlow Run 和运行时模式](./001-adopt-deerflow-run-runtime-patterns.md)
- [ADR-002：采用 DeerFlow 运行时可观测性边界](./002-adopt-deerflow-runtime-observability.md)
- [ADR-003：分离会话与检查点持久化](./003-separate-conversation-and-checkpoint-persistence.md)
- [ADR-004：采用回调优先的 Token 计量](./004-adopt-callback-first-token-accounting.md)
- [ADR-005：已认证身份边界](./005-authenticated-identity-boundary.md)
- [ADR-006：租户隔离与外部工具边界](./006-tenant-isolation-and-external-tools.md)
- [ADR-010：共享工作区存在前使用用户范围](./010-user-scoped-identity.md)
- [ADR-007：流式传输规范 Agent 消息](./007-stream-canonical-agent-messages.md)
- [ADR-008：引入 Agent 应用平台层](./008-introduce-agent-application-platform.md)
- [ADR-009：保持 Platform 与 North 独立](./009-keep-platform-and-north-independent.md)
- [ADR-011：使用按调用准确计量的 Agent 活动](./011-use-call-accurate-agent-activity.md)
