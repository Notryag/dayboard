# Agent 验收

这是执行指南。当前评估权威和分层边界位于
[Agent 评估契约](../current/agent/evaluation.md)。

Agent 验收场景是明确的实时检查，不属于常规测试套件。它们使用真实模型调用，覆盖已部署的 HTTP、队列、Worker、North 运行时、工具、Run 事件和持久化路径。

保持此目录小而面向发布。广泛的模型质量、安全、延迟和 token 指标属于版本化的 [Agent Eval](./agent-eval.md)，而不是此运行器。

运行器默认安全：没有 `--execute` 时只列出场景。执行还需要 `--allow-writes`，因为它会创建持久化 Thread、日历条目、任务、Run、事件和提供商使用记录。测试标题包含每个 Thread 的 `验收<tag>` 前缀作为明确标题文本，使重复运行目录不会产生含糊的变更目标。避免装饰性的方括号标签，因为模型推断简洁标题时可能正确地省略它们。

```bash
cd apps/api
uv run python scripts/agent_acceptance.py

# Run one scenario against a local stack.
uv run python scripts/agent_acceptance.py \
  --execute --allow-writes \
  --scenario multi-create

# Run the catalog against the production HTTPS API after a deployment batch.
export DAYBOARD_ACCEPTANCE_IDENTIFIER=acceptance-user
export DAYBOARD_ACCEPTANCE_PASSWORD='read-from-a-secret-store'
uv run python scripts/agent_acceptance.py \
  --base-url https://dayboard.selfapi.art \
  --execute --allow-writes
```

已认证部署需要专用验收账号。通过 `DAYBOARD_ACCEPTANCE_IDENTIFIER`（或 `--login-identifier`）提供用户名或电子邮件，只能通过
`DAYBOARD_ACCEPTANCE_PASSWORD` 提供密码。运行器只登录一次并复用返回的 session cookie；不会打印密码。不要将这两个值放入已提交的环境文件或 shell history，
并应从 deployment secret store 加载密码。

每个轮次记录终止状态、耗时、预期和实际完成的工具、缺失工具、结果文本、Run ID 和 Thread ID。进程以非零状态退出表示至少一项预期失败。场景在首个失败轮次后停止，以免失败的设置触发无效或昂贵的依赖命令；`skipped_turns` 报告剩余轮次。使用返回的 Run ID 检查其持久化事件。

初始场景包括：

- 从含糊且无标点的行动短语创建相互独立的无日期 Todo items，不创建 calendar entry，也不询问时间；
- 在一条消息中混合创建 calendar/task；
- 对仅包含日期的行动创建 anytime calendar entries，不回退为 task，也不进行 clarification；
- 在一个 Run 中修改和取消多个 calendar entries（`calendar-changes`）；
- 在一个 Run 中完成和修改多个 tasks（`task-changes`）；
- 当变更目标不存在时，拒绝创建替代项。

仅为有意义的产品行为或真实回归添加场景。措辞保持自然，断言聚焦持久化结果，而非模型的确切措辞。
