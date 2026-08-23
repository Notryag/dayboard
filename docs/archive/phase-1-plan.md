# Phase 1 计划

> 已归档：本计划属于历史记录，不描述当前实现。请使用[当前文档](../current/README.md)和[项目状态](../PROJECT_STATE.md)。

状态：已完成。

## 目标

交付最小闭环，证明 Dayboard 可以将 `north` 用作其核心 Agent 能力。

## Phase 1 工作流

```text
user text input
  -> scheduling intent extraction
  -> clarification if needed
  -> create calendar entry or task
  -> confirmation response
```

## 必需组件

1. 包含 `apps/api` 和 `apps/web` 的 App skeleton
2. `north` 依赖接线
3. `CalendarEntry` 和 `TaskItem` schemas
4. PostgreSQL 存储
5. Alembic 迁移
6. 调度工具
7. 最小 prompt 和 intent loop
8. Next.js web 入口
9. 针对 create-calendar-entry 和 clarification flows 的测试

PostgreSQL 是 Phase 1 的存储选择。Dayboard 计划发展为商业产品，因此第一版实现应使用具备生产能力的数据库，而不是 SQLite 或 JSON 文件。

当后台 Agent jobs 和 run streaming 需要 queue/fanout 支持时，应引入 Redis 或 Valkey。它不应作为事实来源。

历史实现遵循[工程指南](../engineering-guidelines.md)。

## 建议的首批里程碑

### M1

- 创建项目包布局
- 接入对 `north` 的本地依赖
- 定义 `CalendarEntry` 和 `TaskItem` models
- 定义 `TenantContext`
- 增加 PostgreSQL session wiring
- 增加 Alembic baseline migration

### M2

- 增加 `create_calendar_entry` 和 `create_task_item`
- 增加 `list_calendar_entries` 和 `list_task_items`
- 通过简单接口返回确定性结果
- 在连接 LLM 前从结构化输入调用 tools
- 增加针对 PostgreSQL 的 repository tests

M2 中增加的任何 command API 都是临时的。在 Agent loop 存在之前，它可以返回硬编码的 clarification，以推动 frontend/API contract 继续演进。M3 中由 `north` 负责 command interpretation 和 clarification 后，必须删除或替换该 fallback。

### M3

- 将 Agent loop 连接到 scheduling tools
- 支持缺少字段时的 clarification
- 端到端验证基于文本的 schedule creation

### M4

- 增加 Next.js command input 和 list views
- 生成或手写第一个 TypeScript API client
- 显示 run status 和 clarification questions

### M5

- 增加 background run worker boundary
- 增加 run event persistence
- 增加用于 run updates 的 SSE endpoint

### M6

- 增加 voice input boundary design
- 确定 ASR provider contract

## 成功标准

当用户可以在 Next.js app 中用自然语言创建 task 或 calendar entry，并在缺少必需字段时获得 clarification、最终收到正确确认时，Phase 1 即成功。

## 测试节奏

使用基于切片的测试。不要等到最后才添加测试，也不要求每个小部分都严格采用 test-first development。

默认节奏：

```text
implement a small vertical slice
  -> add deterministic tests for domain, repository, or tool behavior
  -> add API tests once the endpoint exists
  -> add agent-flow tests after tool behavior is stable
```

对于 Phase 1，确定性测试应先于广泛的 LLM flow tests。`create-calendar-entry` 和 `create-task-item` 路径应当无需调用 model 即可测试。

## 非目标

- 不为每个 tenant 使用独立数据库
- 不包含 billing
- 不包含生产级 organization admin UI
- 不包含 external calendar sync
- 不包含真实 push notifications
- 不包含完整 mobile app

schema 和 service signatures 仍应携带 tenant context，以便未来增加这些能力时无需重写 product tools。
