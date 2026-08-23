# 当前产品模型

Dayboard 是一款自助式、语音优先的日程产品。用户通过语音或文字输入指令，Dayboard 通过 tools 创建或修改 calendar entry 或 task，并在可检查的日视图旁边渲染权威结果。

## 日程分类

分类依据用户表达中的时间锚点：

| 含义 | 产品对象 |
| --- | --- |
| 可解析的日期、时刻或 daypart | Calendar entry |
| 没有时刻或 daypart 的日期 | `anytime` calendar entry |
| 没有可解析的时间锚点 | Undated task |
| “later” 或 “when free”等模糊时间 | Undated task |

示例：

- “明天早上 8 点吃药”会创建一个 08:00 的 timed calendar entry。
- “明天下午提交报告”会使用 afternoon default 创建一个 timed calendar entry。
- “明天提交报告”会为明天创建一个 `anytime` calendar entry。
- “晚点整理资料”会创建一个 undated task。

Daypart defaults 是确定性的，并且仅在 action 被分类为 calendar entry 后应用。当前 defaults 定义在 Agent policy 中，并由 prompt tests 保护。

## 日历条目

一个 calendar entry 有两种 timing shapes 之一：

```text
timed
  timing_kind = timed
  start_time and end_time are timezone-aware timestamps
  scheduled_date is null

anytime
  timing_kind = anytime
  scheduled_date is a product-local date
  start_time and end_time are null
```

公共字段包括 title、可信的 IANA timezone、participants、reminder、status、user scope、audit timestamps 和 Run correlation。Status 为 `scheduled`、`completed` 或 `cancelled`。

如果未提供 duration，timed entries 默认持续一小时。Dayboard 在创建和 rescheduling timed entries 时会自动检查时钟冲突。Anytime entries 没有时钟冲突，也没有 clock reminder。

## 任务项

Task 表示没有可解析时间锚点的 action。它有 title 和 status（`open`、`completed` 或 `cancelled`）。Storage model 仍支持 `due_at`，但当前 Agent classification 会将任何可解析的日期或时间发送到 calendar domain；因此正常的 creation path 会创建 undated tasks。

Tasks 不占据 calendar interval。Task reminder 需要 due timestamp，并锚定到该 timestamp。

## 提醒

Reminder intent 使用 ISO 8601 offset 和 anchor。由 Agent 创建的 timed calendar entries 默认使用 at-start 的 `PT0M` reminder，除非用户禁用或覆盖它。Anytime entries 不会凭空创建 clock reminders。

Application services 会将 schedule changes 与持久化的 reminder-delivery rows 同步。当前 delivery channel 为 `in_app`。Delivery attempts、status、provider identifiers 和 errors 会被存储以供检查。Delivered rows 携带持久化的 per-account `read_at` state。Web header 提供 in-app reminder center，支持 unread count、source-date navigation、read marking、delivery status 和 failed-delivery retry。用户可以在 Web app active 时选择浏览器 Notifications；同一个 reminder ID 在每个 browser session 中只显示一次。Retry 会将 row 返回 `pending`；worker 仍是唯一的 delivery executor。

Delivery lifecycle 是显式的：

| 状态 | 含义 | 用户 inbox |
| --- | --- | --- |
| `pending` | 等待 delivery time 或显式 retry | 隐藏 |
| `processing` | 已由一个 Worker claim | 隐藏 |
| `delivered` | In-app delivery 已完成 | 可见 |
| `failed` | Delivery 已尝试但失败，可以 retry | 可见 |
| `expired` | Calendar reminder 未能在 entry 开始前投递 | 隐藏 |
| `cancelled` | Source 已完成、取消、删除或替换 | 隐藏 |

`read_at` 是独立的 inbox state，不是另一种 delivery status。未来的 timed calendar entries，以及仍处于 delivery grace 内的 entries，可以拥有 pending reminder。Worker 在 calendar start 后提供确定性的 two-minute claim grace，使 at-start `PT0M` reminder 能够跨过 15-second polling interval 和短暂的 scheduling jitter；恰好迟到两分钟仍可投递，之后的任何时间都属于 `expired`，且永远不会再次投递。配置的 reminder offset 刚刚经过的 future entry 可以立即投递。Open task reminders 在 due time 之后仍可操作，也仍然可以投递。
完成、取消、rescheduling 或替换 source 时，会将每个可重试的 active delivery（`pending`、`processing` 或 `failed`）改为 `cancelled`；已经 delivered 的 rows 保留为 reminder history。Completed calendar entries 和 tasks 仍会显示在 schedule view 中，便于用户检查或重新打开。

Delivery queue 不是 user inbox。Web reminder center 只接收 `delivered` 和 `failed` items。每个 inbox item 都从权威的 calendar/task row 投影 source 当前的 title、occurrence time 和 lifecycle status。因此，rescheduled 或 renamed items 会导航到并显示当前 source；cancelled 或 deleted sources 会保留为诚实且不可操作的 history。Source 缺失时会报告为 deleted，而不是静默地把过期 payload data 当作 live schedule item 展示。

## 会话与澄清

Conversation threads 和 messages 是持久化的，并按 user scope 限定。有界 context 和持久化的 compaction summaries 防止每次 model call 都发送完整历史。
Mobile client 在加载历史前，会从 PostgreSQL 解析所有者的 primary Thread。
Device-local storage 永远不决定 conversation ownership，因此其他设备会恢复同一份 durable history，而不会静默创建独立 conversation。
产品为每个 owner 暴露一个 primary conversation。首屏加载最新的 30 条 messages，向上滚动时使用 user-scoped `(created_at, id)` cursor 获取更早的 pages，同时不改变可见的 scroll position。隔离的 evaluation Threads 是 active、non-primary records（`is_primary = false`）；它们不是 product conversations，也不会出现在该 history 中。`active | archived` 只描述 lifecycle，archived Threads 不能接受新的 Runs。

当缺少的信息会实质性地改变结果时，Agent 使用 structured clarification。Dayboard 将问题和可信的 option mapping 持久化到 `conversation_states`。Browser 收到稳定的 option keys 和 display data，而不是 database IDs 或 optimistic-lock versions。持久化的 Interaction 具有 schema identity、source Run、expiry 和单调递增的 state version。选择的 option 会在创建幂等 follow-up Run、lifecycle event 和 user message 的同一个 transaction 中 compare-and-consume 该 exact version。两个相互竞争的 choices 不会同时成功；即使 Interaction 已被 consumed，对同一已接受请求的 retry 仍会返回其现有 Run。

当 target 和 requested action 明确无歧义时，Agent 不会要求确认。

## 身份与所有权

用户可以通过 password authentication 注册。Server-side sessions 使用安全的 `HttpOnly` cookies。Profile records 解析可信的 user、timezone 和 locale context。

每个 conversation、Run、schedule object、transcript、reminder 和 provider usage record 都按 user scope 限定。Browser headers、user text、queued job payloads 和 model arguments 都不能覆盖该 scope。

Scheduling 当前使用可信 account context 解析 local time，默认值为 `Asia/Shanghai`。不支持显式的 foreign-timezone conversion。

产品将该时区显示为 `北京时间`。Model-visible scheduling values 使用不带 offset 的 Beijing local wall-clock time；PostgreSQL 在 UTC session 下将 absolute instants 存储为 `timestamptz`。见 [Time And Concurrency Protocol](time-protocol.md)。

## 产品界面

移动 H5 application 有两个同等重要的 surfaces：

- conversation：用于 voice/text capture、streaming progress、clarification 和 result cards；
- schedule：用于 date rail、chronological agenda、undated tasks、editing、completion、cancellation、settings、appearance 和 logout。

用户通过透明 header 和 horizontal swipe 选择一个 full-width surface。Dayboard 不定义 desktop layout 或 desktop fallback。Conversation schedule cards 不显示 completion checkbox；mutations 可从 detail interaction 中执行。

## 当前范围限制

尚未实现：

- 周期调度引擎；
- 外部日历同步；
- multi-user collaboration 和 organization administration；
- 计费；
- 原生移动应用；
- 外国时区自然语言转换；
- 已安装 PWA 的后台通知投递。

规范的 tool contract 记录在 [agent/tools.md](./agent/tools.md) 中。历史产品阶段仅保留在 [../archive](../archive/README.md) 下。
