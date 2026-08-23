# Token 使用诊断运行手册

状态：活跃运行手册  
最后审阅：2026-07-20

当前的压缩、接收和呈现规则见
[Agent 上下文与记忆契约](../current/agent/context-memory.md)。

已测量的优化里程碑保存在
[agent-token-optimization-history.md](../records/agent-token-optimization-history.md) 中。新增的
缩减数据应追加到该文件，而不是替换早期基线。

## 生产请求路径

配置用户范围内的生产 Dayboard 模型流量遵循以下路径：

```text
Dayboard worker
  -> north agent runtime
  -> Northgate Dayboard gateway
  -> OpenAI-compatible provider gateway
  -> model provider
```

Dayboard 向 Northgate 提供受信任的 `user_id`、`user_id` 和 `run_id` 元数据。North 负责模型调用
和工具调用的运行时行为。Dayboard 负责每个 Run 的持久化业务使用记录。Northgate 负责网关
准入、路由、预留、尝试以及跨应用流量诊断。

生产环境保留直接的提供商 URL 作为回滚配置，但当前两个生产用户范围都已选择使用
Northgate 连接。诊断时仍必须核实实际选中的连接；存在备用 URL 并不能证明请求绕过了 Northgate。

## 2026-07-20 Token 限制事件

一名用户提交了一条简短的日程命令，随后在下一条命令中收到
`TOKEN_LIMIT_EXCEEDED`。该错误来自下一次上游模型调用之前的 Northgate 策略准入，而不是
Dayboard 的按用户提供商预算，也不是上游提供商网关。

成功的 Dayboard Run 发起了两次模型调用：

| 调用 | 实际输入 | 实际输出 | 实际总量 | Northgate 预留量 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 5,028 | 40 | 5,068 | 19,852 |
| 2 | 5,272 | 22 | 5,294 | 20,384 |
| 合计 | 10,300 | 62 | 10,362 | 40,236 |

Northgate 将每次准入的估算值计算为请求体字符数除以 3，再加上配置的默认最大输出量
4,096 tokens。流结束时，这个保守的预留量应由提供商报告的实际用量替换。

但结算并未发生。两条持久化的 Northgate 请求记录停留在 `started`；其中一次尝试也停留在
`started`，另一次则被归类为 `client_disconnected`。因此 Redis 将两个预留量保留为活跃的
`r:<request_id>` 字段，并针对 Dayboard 网关的每日 60,000-token 策略报告 `used=40236`。
下一次约 20,000-token 的预留无法放入额度，因此 Northgate 正确地执行了错误状态。

直接原因是 Northgate 中流式结束处理和策略结算不完整。提高 Dayboard 单独的 token 预算
无法修复此故障。

## 提示词大小与缓存发现

简短的用户消息不是提供商输入 tokens 的主要来源。将运行时上下文移到末尾后，当前
Agent 会发送约 7,623 个字符的系统指令，以及分布在 11 个工具描述和 JSON schema 中的
9,094 个字符。离线 `o200k_base` 计数估算它们分别为 1,640 和 2,077 tokens，即在会话消息
和协议开销之前已有 3,717 个固定 tokens。Provider 报告的用量仍是权威数据。写入命令通常
需要在工具结果之后再次进行模型调用，因此未使用提示词缓存时，大部分固定上下文会被
发送两次。

第一次模型调用使用了 5,028 个输入 tokens。工具调用后的请求使用了 5,272 个，只多出 244
个，这说明第二轮的主要开销是重复的固定上下文，而不是返回的工具 payload。系统提示词还
将微秒精度的当前 datetime 放在接近开头的位置，位于几乎所有静态规则之前。这样的安排使
请求前缀在每个 Run 中都发生变化，无法让较长的规则块成为跨 Run 稳定的缓存前缀。
现在运行时调度上下文位于静态规则之后；其内容和调度语义未变。

受影响的 thread 在第一次模型调用前有 13 条消息：4 条 human、6 条 AI 和 3 条 tool 消息。
它们的文本内容共 1,091 个字符，其中包括 986 个字符的历史工具结果，以及约 300 个字符的
历史工具调用参数。在第二次模型调用前，本次写入又增加了 64 个字符的工具参数和一个
426 字符的工具结果。这证明已完成的工具 payload 是 thread history 中增长最快的部分。North
现在使用 OR 语义，将 Dayboard 的 1,200-token 历史阈值与 40-message 硬上限结合起来。
Compaction 仍保留最近完整的 AI/tool 对，Dayboard 可见的 conversation history 仍与运行时检查点
相互独立。摘要生成是一次真实的模型调用，并非免费的预处理；North 将其标记为
`middleware:summarization`，使其用量仍可归属于同一个 Run，并可根据测得的净节省量调整阈值。

提供商网关为两次成功调用都记录了 `cached_tokens=0`。Northgate 的 exact-response 缓存
在 Dayboard 网关中也处于禁用状态。这是两个独立的机制：

- Northgate exact cache 会复用完整且完全相同的请求和响应。工具结果前后的 Agent 调用并不
  相同，因此它不是此工作流的主要优化手段。
- 提供商提示词缓存可以复用稳定的提示词前缀，同时仍执行新的 completion。本次 Run 没有
  报告 cache-read 用量。

缺少提供商提示词缓存命中会增加成本和延迟，但它不是 2026-07-20 被拒绝的原因；原因是
过期的 Northgate 预留量。

同一个 `gpt-5.4-mini` 兼容路径曾报告 3,840 至 5,120 tokens 的历史提示词缓存读取，其中
包括经过同一上游账号的流量。因此缓存计量路径本身有效，但本次 Run 的第二次调用没有复用
预期的稳定前缀。现有的内容最小化日志无法区分提供商缓存准入、上游路由行为或请求序列化
差异。不要将 Northgate exact-response caching 作为替代方案：对于响应可能包含写入工具调用
的 Agent，重放完整模型响应不是合适的默认行为。

已部署的 sub2api 兼容路径支持 `prompt_cache_key`，并会在客户端未提供时自动推导
该值。当前推导会包含完整的系统消息和第一条用户消息。因此，即使请求共享同一个较长的
静态前缀，Dayboard 的运行时 datetime 和每条新命令仍会改变该路由 key。现在 Dayboard
为 `openai:` 模型提供显式的带版本 key，并根据受信任用户身份的 hash 确定性地划分为 32 个
分片。key 中不会发送原始身份。这样，同一用户的两次模型调用及后续 Runs 都能使用稳定的
缓存路由，同时避免形成一个全局热点 key。Northgate 继续记录提供商报告的缓存读取，以便
测量实际效果，而不是凭假设判断。

## 工具面与提示词缩减

Dayboard 暴露 7 个日程工具，以及运行时交互工具：

| 区域 | 工具 |
| --- | --- |
| 日历 | `create_calendar_entry`, `search_calendar_entries`, `reschedule_calendar_entry`, `cancel_calendar_entry` |
| 任务 | `create_task_item`, `search_task_items`, `update_task_item` |
| 交互 | `ask_clarification` |

这是一个完整统一的日程工具面，而不是 11 个可以独立加载的插件。将工具说明移入 skill
并不会从模型请求中移除可执行的 JSON schema。工具选择器还会在大多数简短命令前增加一次
模型调用，而提供商原生的延迟工具加载在当前 OpenAI-compatible gateway path 上尚未得到验证。

Dayboard 改为采用确定性的分阶段加载。第一次语义/操作轮会收到全部 7 个日程工具以及
`ask_clarification`。成功的日历搜索会将下一轮缩小为 4 个日历工具加 clarification；任务
搜索会将其缩小为 3 个任务工具加 clarification。混合领域批次保留完整工具面。成功的终结
写入会在确认阶段移除日程工具。第一次 malformed/error result 会恢复完整工具面；同一用户
回合中的第二次失败会移除工具，让模型解释失败原因而不是循环调用。这个过程不需要关键词
路由器或额外的模型调用。

一次 live no-write comparison 使用了 6 条有代表性的命令：创建日历、无日期任务、截止日期
任务、混合创建、重新安排日历和取消任务。所有工具调用都由真实模型选择，但没有执行任何
调用。在保留行为契约的同时压缩重复的策略文本
后，离线估算的固定大小变化如下：

| 固定输入 | 初始 | 压缩提示词的 11-tool | 统一的 7+1 | 当前 temporal rule |
| --- | ---: | ---: | ---: | ---: |
| 系统提示词 | 1,640 | 897 | 903 | 861 |
| 工具 schemas | 2,077 | 1,797 | 1,556 | 1,341 |
| 合计 | 3,717 | 2,694 | 2,459 | 2,202 |

当前固定工具面比初始 baseline 小 40.8%，比统一的 7+1 版本小 10.5%。任务 schema 不再
暴露日期/时间字段，因为所有可解析的时间锚点现在都会路由到日历条目。

提供商报告的第一轮输入从 4,707-4,716 tokens 降至 2,915-2,943 tokens，约减少 38%。5 个
压缩提示词案例最初与 baseline 一致。重新安排案例暴露出一个回归：系统将目标日期用作搜索
窗口；增加明确的原始日期规则后修复，针对性的 live rerun 选择了正确的原始日期。最终 6 条
语义路由与 baseline 一致。每个变体中的重复调用都报告了提示词缓存读取（之前为 4,608，
之后为 2,560），确认更小的稳定前缀仍可缓存。

随后使用相同的 6 个 live no-write 案例检查 7+1 工具面。所有路由均匹配：创建日历、创建无
日期任务、创建截止日期任务、混合日历/任务调用、在原始时间区间内进行日历搜索，以及不带
`purpose` 的任务搜索。提供商报告的第一轮输入为 2,805-2,814 tokens，比压缩的 11-tool 版本
又减少 101-138 tokens；第一次调用后读取到 2,560-token cache。

两次 live synthetic-result check 在不执行写入的情况下测试了缩小后的第二轮。日历 4+1
子集使用 2,615 个输入 tokens，选择了带有权威 ID、`expected_updated_at` 和请求目标时间的
`reschedule_calendar_entry`。任务 3+1 子集使用 2,428 个输入 tokens，选择了带有
`new_status=cancelled` 和 `expected_updated_at` 的 `update_task_item`。这验证了领域缩小
能保留变更路径和乐观锁字段。

又使用 6 个 live no-write 案例检查绝对时间规则。仅包含日期的完成事项、明确表示 before 的
措辞以及仅包含日期的杂事，都使用确定性时钟选择了创建日历。无时间和模糊时间的操作选择了
创建任务，混合消息则同时选择了两者。提供商报告的第一轮输入为 2,566-2,573 tokens，第一
次调用后读取到 2,048-token cache。

一次独立的 live two-round write simulation 使用了合成的成功工具结果，且没有写入数据库。从
最终确认轮移除 schema 后，实际输入从 4,908 降至 3,501 tokens，节省 1,407 tokens。no-tools
前缀预热后，报告了 3,328-token cache read。这支持仅在终结阶段裁剪工具，同时不会削弱初始
语义路由能力。

## 必需诊断

Northgate 运维诊断应在不记录请求内容的前提下提供：

- 按 `run_id` 等已认证的元数据维度查询；
- 请求和提供商尝试的结果；
- 准入时估算或预留的 tokens；
- 已结算的提示词、completion 和 total tokens；
- 提供商报告的缓存提示词 tokens；
- exact-cache 结果（`bypass`、`miss`、`hit` 或 `error`）；
- 适用时提供策略拒绝代码以及 remaining/reset headers。

MCP server 不是这些数据的事实来源。运维 HTTP API 和 PostgreSQL records 必须先完整。后续
可以增加 MCP adapter 来包装这些运维 API 以提供便利，但不能让它接收数据库或提供商密钥。

## 验证标准

当程序化测试证明以下各项时，Northgate 修复才算完成：

1. 成功消费的流会结算请求和尝试记录。
2. 如果已经观察到终结用量事件，下游断开时仍会结算提供商报告的用量。
3. 没有权威用量的断开会保持保守行为，不会臆造实际 tokens。
4. 策略预留字段会且仅会一次转换为已结算字段。
5. 运维人员可以解析某个 Dayboard `run_id` 的全部模型调用，并区分预留量、实际用量、提供商
   提示词缓存和 exact cache 行为。
