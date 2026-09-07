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
  -> successful search or write
       -> return receipts to model; continue remaining work with the full tool surface
  -> failed tool batch
       -> one recovery round, regardless of the number of failed calls in the batch
  -> consecutive failed recovery batch
       -> remove tools and explain completed and unresolved work accurately
  -> fully successful batch
       -> reset the consecutive-failure counter
  -> clarification request
       -> current Run ends as needs_clarification
       -> answer creates a new Run on the same Thread
```

最近一批写入成功不代表整条用户指令完成。Agent 必须能继续执行依赖前一步结果的操作，以及跨日历/任务领域的操作。模型负责判断是否还有剩余工作；确定性回执和呈现工件仍是写入事实来源。不得重放已成功的写入。

失败预算按连续失败的工具批次计算，而不是按 ToolMessage 数量累计。同批多个失败只消耗一次尝试；完整成功的批次结束本次恢复阶段。Run 级模型调用次数和 token 预算另外限制搜索循环及反复成功/失败的路径，见 [Run 生命周期](../run-lifecycle.md#用量与预算)。

## 呈现与安全

面向用户的确认是简洁的纯文本；权威对象则单独渲染为类型化卡片。模型/工具生命周期诊断载荷和秘密绝不会进入用户 SSE。工具呈现工件在发布和持久化前会在 Dayboard 边界进行校验。

## 验证映射

- 提示词分类和交互规则：
  [`prompts.py`](../../../apps/api/src/dayboard/agent/prompts.py) and
  [`test_agent_prompts.py`](../../../apps/api/tests/test_agent_prompts.py).
- 完整工具面、按批恢复、继续执行和模型可见脱敏：
  [`middleware.py`](../../../apps/api/src/dayboard/agent/middleware.py) and
  [`test_agent_middleware.py`](../../../apps/api/tests/test_agent_middleware.py).
- 工具 schema 和产品操作：[tools.md](./tools.md) 以及
  [`test_agent_tools.py`](../../../apps/api/tests/test_agent_tools.py).
- 持久化澄清和 Run 语义：[run-lifecycle.md](../run-lifecycle.md)。
- 广泛的实时模型行为和发布门禁：[evaluation.md](./evaluation.md)。
