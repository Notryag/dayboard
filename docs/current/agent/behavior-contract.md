# Agent 行为规范

状态：当前规范（规范版本）  
最后验证：2026-08-23

## 范围与权威

Dayboard 的 Agent 将自然语言调度意图转换为类型化产品操作。模型可以分类、选择并提出工具参数，但只有服务器端工具事务成功时才会改变产品状态。PostgreSQL 实体及其 `row_version` 值是权威来源；助手文本、摘要、检查点和工具工件都不是权威来源。

可信的 `UserContext`、Run 身份、授权、幂等身份、区域设置和默认时区都在模型外部注入。用户文本不能替换这些字段，模型可见的 schema 也不会暴露它们。

## 分类与时间

| 用户意图 | 必需行为 |
| --- | --- |
| 不含时刻/时段的具体日期 | 创建 `anytime` 日历条目；绝不臆造时刻。 |
| 含时刻/时段的具体日期 | 使用北京时间本地模型字段创建定时日历条目。 |
| 无法解析的时间锚点 | 创建无日期任务。 |
| `晚点` 或 `有空` 等模糊时间 | 视为没有具体时间锚点；绝不臆造日期。 |
| 明确的外国时区 | 说明不受支持，不写入。 |
| 多个独立操作 | 每个操作发出一个类型化调用，并保留所有操作。 |

相对日期根据紧邻当前用户消息之前插入的可信运行时表解析。面向模型的本地字段永远不包含偏移量。完整的时间边界规则见[时间协议](../time-protocol.md)。

## 搜索、澄清与变更

- 修改和取消必须先搜索。搜索使用原始目标线索，而不是请求中的目标值。
- 只有一个明确匹配项时直接继续。没有匹配项时不写入，也绝不创建替代项。存在多个合理匹配项时，使用 `ask_clarification` 提供简洁选项。
- 只有缺失信息会实质性改变结果时才需要澄清。纯文本不能替代持久化交互协议。
- 序列引用先搜索锚点。创建时使用 `anchor_entry_id` 和 `expected_anchor_row_version`；服务器锁定权威锚点并据此推导。
- 变更使用所选实体的 `row_version`。授权、校验、冲突检测、事务性和幂等性由服务器负责。
- Agent 绝不能声称工具成功的规范结果中不存在的写入、对象状态或冲突。

## 工具循环状态机

```text
new user turn
  -> full scheduling + clarification tool surface
  -> successful search
       -> same-domain tools + clarification
  -> successful terminal write batch
       -> deterministic localized completion; no extra model call
  -> malformed or failed result
       -> restore full surface for one recovery attempt
  -> second failed result in the same user turn
       -> remove tools, stop tool retries, and let the model explain the failure
  -> clarification request
       -> current Run ends as needs_clarification
       -> answer creates a new Run on the same Thread
```

混合领域批次在解决前保留完整工具面。搜索结果、错误、部分完成结果和未解决工作会返回模型。成功的终止写入根据经过校验的回执完成，因此模型不能改写已提交的结果。

## 呈现与安全

面向用户的确认是简洁的纯文本；权威对象则单独渲染为类型化卡片。模型/工具生命周期诊断载荷和秘密绝不会进入用户 SSE。工具呈现工件在发布和持久化前会在 Dayboard 边界进行校验。

## 验证映射

- 提示词分类和交互规则：
  [`prompts.py`](../../../apps/api/src/dayboard/agent/prompts.py) and
  [`test_agent_prompts.py`](../../../apps/api/tests/test_agent_prompts.py).
- 工具循环收窄、恢复、终止完成和模型可见脱敏：
  [`middleware.py`](../../../apps/api/src/dayboard/agent/middleware.py) and
  [`test_agent_middleware.py`](../../../apps/api/tests/test_agent_middleware.py).
- 工具 schema 和产品操作：[tools.md](./tools.md) 以及
  [`test_agent_tools.py`](../../../apps/api/tests/test_agent_tools.py).
- 持久化澄清和 Run 语义：[run-lifecycle.md](../run-lifecycle.md)。
- 广泛的实时模型行为和发布门禁：[evaluation.md](./evaluation.md)。
