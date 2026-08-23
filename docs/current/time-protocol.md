# 时间与并发协议

状态：当前规范契约  
最后审阅：2026-07-23

## 不变量

Dayboard 当前支持一个可信的调度时区。其产品名称为 `北京时间`，机器标识符是 IANA 时区 `Asia/Shanghai`。

| 边界 | 表示 |
| --- | --- |
| 产品显示 | 北京时间 |
| 模型可见的工具输入和回执 | 北京本地墙上时钟值，不带偏移 |
| 应用/领域层 | 带时区的 Python `datetime` |
| PostgreSQL | `timestamp with time zone`，使用 UTC 数据库会话操作 |

`Asia/Shanghai` 仍是内部 IANA 标识符。不得在全局范围用显示标签或非标准时区名称替换它。PostgreSQL 存储绝对时刻；独立的 `timezone` 列保留用于显示和本地日期语义的可信业务时区。

全天日历条目将 `scheduled_date` 存储为 PostgreSQL `date`。它没有虚构的时钟时刻，因此不进行 UTC 转换。

## 模型可见契约

模型只读取和写入北京本地墙上时钟值：

```json
{
  "id": "calendar-entry-id",
  "title": "钓鱼",
  "local_start": "2026-07-24T16:00",
  "local_end": "2026-07-24T17:00",
  "row_version": 3
}
```

规范精度为分钟，格式为 `YYYY-MM-DDTHH:mm`。模型可见的本地字段绝不包含 `Z`、`+00:00`、`+08:00`、IANA 时区或 UTC 时间戳。模型不得加减八小时。可信运行时代码在工具边界附加 `Asia/Shanghai`，并转换所得时刻进行存储。

时长请求使用时长，而不是由模型计算结束时间：

```json
{
  "calendar_entry_id": "calendar-entry-id",
  "new_duration_minutes": 30,
  "expected_row_version": 3
}
```

明确的时钟变更使用相同格式的 `new_local_start` 或 `new_local_end`。日历搜索、创建、变更和冲突回执，任务截止回执，澄清恢复消息以及系统参考时钟都必须遵循这一仅本地值规则。

同一个模型上下文绝不能同时包含绝对字段及其本地等价字段，例如同时包含 `start_time=08:00+00:00` 和 `local_start=16:00`。

## ToolMessage 边界

```text
ToolMessage.content  -> compact local-time receipt for the model
ToolMessage.artifact -> complete UTC/offset-aware entity for UI, SSE, and history restoration
```

工件可以包含 `start_time`、`end_time`、`due_at`、`timezone` 和审计时间戳。工件数据绝不能序列化到提供商请求中。提供商边界测试必须检查实际发送给模型的消息，并拒绝 ToolMessage 内容中的绝对调度时间戳。

结构化澄清会为 UI 存储完整的呈现候选项。选定候选项恢复 Agent 执行时，Dayboard 创建只包含本地字段和 `row_version` 的模型候选项；不得将工件时间戳复制到生成的用户消息中。

## 数据库转换

可信转换由程序负责：

```python
local_value = datetime.strptime(value, "%Y-%m-%dT%H:%M")
aware_value = local_value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
```

SQLAlchemy 将带时区的值发送给 PostgreSQL `timestamptz`。PostgreSQL 规范化该时刻；生产数据库会话时区为 UTC。读取结果返回带时区的时刻，只有在构建模型回执或产品显示值时才转换回 `Asia/Shanghai`。

浏览器 REST API 可以携带带偏移的时刻，因为它们属于类型化 UI/工件边界，而不是模型边界。浏览器渲染必须使用可信账户时区，而不是设备时区。

## 乐观并发

调度实体使用整数数据库版本，而不是审计时间戳：

```sql
row_version BIGINT NOT NULL DEFAULT 1
```

每次有效的日历或任务变更都原子地应用：

```sql
UPDATE ...
SET row_version = row_version + 1,
    updated_at = now(),
    ...
WHERE id = :id
  AND row_version = :expected_row_version
RETURNING *;
```

更新行数为零表示所选实体发生了并发变化。`updated_at` 仍可用于审计和排序，但不是并发令牌。模型工具使用 `expected_row_version`，序列创建使用 `expected_anchor_row_version`。检查锚点行的版本、活动状态和权威 `end_time` 时，该行会保持锁定。

所有变更路径都会递增版本：Agent 重排/取消/更新、Web 编辑/取消、日历完成/重新打开，以及任务完成/重新打开/取消。

## 运行时上下文隔离

Agent 检查点使用 `dayboard-time-v2` 命名空间。每次主模型请求前，提供商边界脱敏都会移除 UI 工件并重写绝对调度字段。摘要输入只包含紧凑的本地时间回执，因此 UTC 工件值不会进入模型上下文。

## 必需测试

测试必须证明：

1. 本地输入和回执字段使用相同的 `YYYY-MM-DDTHH:mm` 格式。
2. 由工具代码而非模型附加 `Asia/Shanghai`，并由 PostgreSQL 存储正确时刻。
3. 模型回执不包含 `start_time`、`end_time`、`due_at`、timezone、`Z` 或数字偏移。
4. UI 工件保留完整绝对时间戳，刷新后渲染保持一致。
5. 发往提供商的消息绝不包含工件调度时间戳。
6. 时长更新只修改选定条目，除非明确请求其他变更。
7. 相邻条目彼此独立；缩短第一个条目会产生间隔，不会移动下一个条目。
8. 每次变更都会递增 `row_version`，过期版本会原子失败。
9. 锚点创建会拒绝过期的 `expected_anchor_row_version`。
10. 澄清恢复只发送本地字段和版本。
