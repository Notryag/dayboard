# 工程指南

## 核心原则

- 保持 `north` 和 `agent_platform` 为彼此独立的底层依赖。Dayboard 按 ADR-009 负责二者的桥接；任一底层都不得导入另一底层或 Dayboard。
- 不要将 Dayboard 产品概念放入 `north` 和 `agent_platform`。
- 除非只是引用（如 `run_id`），不要将 `north` 运行时概念放入 Dayboard 业务模型。
- 将 PostgreSQL 视为事实来源。
- 将 Redis 或 Valkey 视为队列、扇出、锁、限流和缓存的基础设施。
- 从首次实现开始就明确用户隔离和用户上下文。
- 对基础设施、协议、解析、UI 原语和生成客户端，优先使用成熟现有库，而不是自定义实现。

## 先设计持久不变量

不要把基础数据和架构决策当作临时实现细节。在编写跨越持久化或服务边界的功能前，先确定产品增长后仍必须正确的不变量。这一层的捷径代价很高，因为同一假设会扩散到迁移、repository、领域模型、API schema、生成客户端、Agent 工具、提示词、缓存上下文、测试和生产数据。之后修正它将是全系统协议迁移，而不是局部重构。

在编写第一个 schema 或公共规范前，检查以下问题：

1. 哪个是权威事实来源，每次转换由谁负责？
2. 每个字段是否恰好承担一种语义职责？
3. 事务、并发、幂等和用户隔离保证是什么？
4. 数据库、服务、API、模型和 UI 边界分别应使用哪种表示？
5. 哪些约束和索引能使无效状态不可能出现，并让预期访问路径高效？
6. 在真实并发下，设计如何迁移、回滚、恢复并保持可观测？
7. 设计是否通过稳定边界实现可扩展，而不是依赖推测性抽象或兼容分支？

选择已知需求支持的最强简单设计。“可扩展”不意味着构建未使用的通用性，而意味着保持清晰的所有权、单一用途字段、明确不变量和可替换边界。优先保证基础正确性，再追求交付速度，同时允许展示等低成本细节渐进演化。

调度并发重设计是一个参考示例。`updated_at` 最初被复用为乐观锁令牌，尽管它其实是审计字段。这使并发正确性与时间戳精度、数据库更新行为、时区/序列化规则和客户端往返耦合在一起，也让较长的时间戳穿过 REST 和模型工具 schema。用 `row_version` 替换它需要协调数据库、repository、API、生成的 TypeScript、Agent 回执、提示词、检查点和测试变更。从第一次迁移开始使用专用整数版本会更正确且成本更低：审计时间回答行何时变化，而 `row_version` 回答它是否仍是之前读取的确切版本。

时间表示暴露了同类错误。让 UTC 实体和北京本地值进入同一个模型上下文，会让模型负责转换，并可能使八小时偏移变成虚假的调度冲突。持久化设计为每个边界分配一种表示：模型使用北京本地墙上时钟值，应用代码使用带时区的 datetime，PostgreSQL 使用 UTC 时刻，完整绝对实体只存在于 UI 工件中。见[current/time-protocol.md](./current/time-protocol.md)。

## 文档边界

- `docs/current/` 是唯一规范的全系统描述。实现契约变更时，在同一提交中更新相关 current 文档。
- `docs/current/agent/` 负责当前 Agent 行为、工具、上下文/记忆和评估契约。提示词实现这些契约，但不是唯一规范。
- `PROJECT_STATE.md` 仅限于当前版本、已完成工作、下一里程碑、已知问题和发布检查。不要追加实现时间线。
- ADR 背景本质上是历史性的。高成本决策改变时新增或取代 ADR；不要持续改写已接受决策，使其看起来像当前状态文档。
- 将面向任务的开发和 Eval 流程放在 `docs/guides/`，生产运行手册放在 `docs/operations/`，测量或实验依据放在 `docs/records/`。
- `docs/plans/` 只保留未完成的活动工作；提取仍然有效的当前契约后，将计划归档到 `docs/archive/`。
- `docs/archive/` 下的文件绝不指导实现，并且必须明确标记为已归档。
- 每个事实只由一个文档负责。指南、运行手册、记录、计划和包 README 应链接到当前契约，而不是重复内容。不要维护单独的 Wiki 副本。

## 优先使用脚手架

存在官方或成熟的脚手架时，使用它。

示例：

- 使用 Next.js CLI 创建 Next.js
- 使用 Alembic 命令创建迁移
- 选用 shadcn/ui 时使用 shadcn CLI 添加组件
- API 稳定后从 OpenAPI 生成 TypeScript API 客户端

不要手动重建维护良好的工具可以生成的大型样板代码。

生成代码可以调整以适应项目，但大型生成工件应与手写应用代码保持隔离。

## 构建前先复用

实现非平凡功能前，按以下顺序检查：

1. Python 或 TypeScript 标准库
2. 现有 Dayboard 代码
3. 现有 `north` 能力
4. 成熟的开源库
5. 自定义实现

不要为以下内容重复实现已有功能：

- 日期和时区处理
- schema 校验
- 数据库迁移
- 队列和 Worker
- SSE 客户端
- OpenAPI 客户端
- 表单处理
- UI 原语
- 日历显示组件
- ASR 提供商客户端

如果第三方依赖能降低真实实现风险并且边界清晰，鼓励添加。优先选择活跃维护、API 清晰、规模合理且锁定程度低的库。稳定性、可运维性和可维护性比减少依赖数量更重要。

适合复用的候选项包括：

- UI 原语和组件系统，例如 Radix UI 和 shadcn/ui
- 图标，例如 lucide-react
- 服务端状态和缓存，例如 TanStack Query
- 本地/客户端状态，例如 Zustand 或 Jotai
- 表单和校验适配器，例如 React Hook Form 和 Zod
- 日期、时区和日历 UI 库
- 表格、虚拟列表、上传组件、录音组件和 SSE 客户端
- 从 OpenAPI 生成 API 客户端

除非产品有现有库无法满足的明确需求，否则避免构建这些功能的自定义版本。

在 ADR 中记录重大的依赖选择。

依赖规则：

- 可以自由使用成熟库交付产品，但在可行时将其隔离在功能或基础设施边界之后。
- 不要让 UI 库定义后端契约或领域模型。
- 不要立即包装每个库。只有在需要保护业务代码、提供商选择或生成契约时才进行包装。
- 对提供 CLI 的库（例如 shadcn/ui），优先使用 CLI 安装和生成式配置。
- 添加配置命令变化快或存在破坏性更新的库前，先查看当前文档。

## 后端分层

包级别的所有权由 [ADR-008](./adr/008-introduce-agent-application-platform.md) 和
[ADR-009](./adr/009-keep-platform-and-north-independent.md) 定义：North 负责运行时原语，
`agent_platform` 负责可复用的应用能力，Dayboard 负责调度产品语义。North 和 Platform 是彼此独立的底层依赖；Dayboard 负责二者的桥接。包边界位于下面这些 Dayboard 内部后端层之上。

目标后端布局：

```text
dayboard/
  api/
  app/
  agent/
  domain/
  tools/
  db/
  workers/
  integrations/
```

职责：

- `api`：HTTP 路由、SSE 路由、请求和响应 schema
- `app`：用例和编排
- `agent`：`north` 集成、提示词、Agent 构建
- `domain`：业务模型、策略、校验
- `tools`：面向 Agent 的轻量适配器
- `db`：SQLAlchemy 模型、repository、会话、迁移
- `workers`：后台作业
- `integrations`：ASR、对象存储、外部 API

目标内部依赖方向：

```text
api/workers --------> app
agent/tools --------> app + domain + North
app ----------------> domain + declared ports
db/integrations ----> declared ports + domain
```

箭头从消费者指向它导入的内容。`domain` 不得导入 `app`、`api`、`db`、`workers`、Agent 工具、FastAPI、SQLAlchemy 或 North。应用用例依赖 ports，而不是具体 repository；基础设施适配器实现这些 port，并且只在 composition root 中连接。现有违规会按垂直切片移除，然后由架构检查器锁定。

避免：

- API 路由中的业务规则
- 散落在 repository 之外的原始 SQL
- 包含完整业务工作流的工具函数
- `north` 导入 Dayboard 代码
- Platform Core 导入 SQLAlchemy、FastAPI、产品模块或具体提供商
- 应用服务暴露 SQLAlchemy 行，或依赖隐式共享 Session 契约
- 使用未版本化的任意映射作为公共工件或交互协议
- 将请求上下文存储在全局可变状态中

## 工具设计

Agent 工具应当范围小且明确。

优先：

```text
create_calendar_entry
search_calendar_entries
reschedule_calendar_entry
cancel_calendar_entry
create_task_item
search_task_items
update_task_item
```

避免：

```text
manage_calendar(action, payload)
```

工具函数应当轻量：

```text
tool input
  -> Pydantic validation
  -> application/domain service
  -> repository
  -> structured tool result
```

LLM 响应不是事实来源。通过工具创建的数据库行才是事实来源。

## 用户上下文

在产品使用共享数据库部署时，服务和工具边界接受不可变的 `UserContext`。

```text
UserContext:
  user_id
  timezone
  locale
```

规则：

- `user_id`、timezone 和 locale 必须来自可信服务器上下文。
- 模型不得生成用户、权限或 Run 身份字段。
- Repository 查询必须包含 `user_id`。
- 工具输入 schema 不得暴露可信上下文字段。
- 未来的共享 Workspace 必须作为真正的授权模型引入，而不是作为未使用的存储路由标志。

## 数据库规则

- 使用 PostgreSQL 和 Alembic 进行产品持久化。
- 持久化使用 SQLAlchemy 模型，API/工具 schema 使用 Pydantic 模型。
- 将 SQLAlchemy 模型与 API 响应 schema 分离。
- 写入使用事务。
- 带有 `deleted_at` 的业务对象使用软删除。
- 外部文件存储在对象存储中；PostgreSQL 只存储 URI 和元数据。
- 保持迁移可重放并经过代码审查。
- 首次生产发布后，绝不要重写可能已经执行过的迁移含义。即使根据修改后的历史构建的干净数据库看起来正确，也要用新的正向迁移修复已部署的 schema 漂移。
- 首次生产发布前，可以将迁移历史明确压缩为一个经过审查的基线。该基线复用已部署的 head revision，使现有开发数据库和全新安装无需运行时兼容分支或手动 stamping 即可收敛。合并前同时验证现有数据库和空 PostgreSQL 数据库。
- 保持 PostgreSQL 物理类型和索引、SQLAlchemy 元数据以及 Alembic 历史一致；在 CI 中用 `alembic check` 强制检查所属 schema 漂移。
- 通过明确的所有权过滤器声明由外部运行时或提供商创建的表。不要广泛抑制未知 schema 差异，也不要逐项忽略。

常见业务表字段：

```text
created_at
updated_at
deleted_at
created_by_run_id
updated_by_run_id
```

时间规则：

- 面向 Agent 的调度工具接受不带 `Z` 或数字偏移的本地日期/时间值。
- 在 Dayboard 边界使用可信的 `UserContext.timezone` 解析本地值；绝不接受模型或单条命令浏览器输入所拥有的时区。
- 通过该边界后使用带时区的 datetime。
- 在 PostgreSQL 中将规范时间戳存储为带时区的值。
- 单独存储可信用户的 IANA 时区，例如 `Asia/Shanghai`。
- 自然语言时间解析必须使用明确的参考时间和时区。

## API 规则

- 使用 Pydantic 请求和响应 schema。
- 不要返回原始 SQLAlchemy 模型。
- 使用稳定的错误封装。
- 长时间运行的 Agent 工作应使用 `agent_runs` 和后台 Worker。
- 命令创建及其他可重试写入端点使用 `Idempotency-Key`。
- 通过 `GET /api/runs/{run_id}` 暴露 Run 状态。
- 实现流式传输后，通过 SSE 暴露实时 Run 更新。
- 在面向用户的写入和命令端点的 API 边界应用限流。
- 在服务器环境中使用 Redis 或 Valkey 保存共享限流状态。
- 不要只依赖前端节流来控制成本或滥用。
- 绝不要使用调用方提供的用户 header 作为限流或授权身份。
- 为每个 HTTP 请求生成或校验请求 ID，并在 `X-Request-ID` 中返回。
- 会话解析后，将已认证用户 ID 绑定到结构化请求日志。
- 将排队的 Agent 工作与 Thread 和 Run ID 关联；持久化 Run 事件是用户可见的执行记录，日志是运维诊断记录。
- 绝不要记录密码、密码哈希、原始会话令牌、cookie、授权 header、原始音频或完整命令文本。

建议的错误形状：

```json
{
  "error": {
    "code": "missing_required_field",
  "message": "需要开始时间。",
    "request_id": "req_..."
  }
}
```

## Agent 与 LLM 规则

- 工具创建和变更数据；普通模型文本不会。
- 工具 schema 应当范围小、有类型且清晰。
- 缺少必需调度字段时应触发澄清，而不是不安全地猜测。
- 业务规则属于代码，不能只存在于提示词中。
- 提示词应说明如何使用工具以及何时澄清。
- 工具结果应当结构化且适合 UI。
- 模型/提供商专用代码应保持在 `north` 或集成边界之后。
- 记录 Run 元数据、工具名称、工具参数、结果、对象 ID、错误和延迟。
- 不要记录秘密、原始提供商 token 或不必要的敏感音频载荷。
- 防止可信上下文受到提示词注入。用户文本不能覆盖用户、权限或系统上下文。
- 只从环境变量或秘密存储加载模型凭据和 gateway URL。
- 不要提交真实的 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、提供商密钥或复制的本地 Codex 凭据。
- 通过 `.env` 中的 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 等变量支持 OpenAI 兼容转发。
- 启用真实 LLM 命令执行前，增加提供商级请求/token 预算。

良好的工具结果形状：

```json
{
  "type": "calendar_entry_created",
  "calendar_entry": {
    "id": "cal_...",
    "title": "Product review",
    "start_time": "2026-07-22T15:00:00+08:00",
    "updated_at": "2026-07-20T09:00:00Z"
  },
  "conflicts": []
}
```

## 前端规则

首版 UI 使用 Next.js、React 和 TypeScript。

建议的布局：

```text
app/
components/
features/
lib/api/
lib/types/
```

规则：

- 页面负责组合数据和布局。
- 复杂 UI 放在功能组件中。
- 数据获取放在 API/客户端辅助函数或路由级 loader 中。
- 不要将原始 fetch 逻辑散落在组件中。
- OpenAPI 生成可用后，不要手工重复 API 类型。
- 时间显示统一通过共享格式化辅助函数处理。
- 组件要考虑移动端，同时将响应式 Web 应用作为当前客户端。
- 首个页面应是移动优先的会话界面：上方是消息历史，下方是文本输入和语音操作。
- shadcn/ui 适合作为首个组件系统，因为它在 Radix 原语之上提供可编辑的本地组件。
- 有可用实现时使用 lucide-react 图标，不要手绘 SVG 图标。
- 在设计功能组件样式前，将主题决策放入 CSS 变量或 shadcn 主题令牌。
- 避免在 React 组件中硬编码品牌色、间距、阴影或圆角。
- 当状态在相距较远的组件之间共享时，使用专用状态工具。局部 UI 优先使用简单 React 状态，服务端状态使用 TanStack Query，跨组件客户端状态使用 Zustand 或 Jotai。
- Agent Run 状态和持久化调度数据由服务器提供。前端状态不应成为第二事实来源。

当 React 文件表示内聚的 UI 时，可以比后端文件更大。如果页面或复杂组件只有一个明确职责，约 400–500 行是可以接受的。

在以下情况下评估拆分：

- React 文件超过 500 行
- 一个文件混合 API 调用、复杂状态、业务规则和布局
- hook 超过 150 行
- 组件包含多个无关的交互模式
- 由于耦合了过多关注点而难以设置测试

## 文件大小与拆分

将这些作为评审触发条件，而不是硬性失败条件。

Python：

- 文件超过 300 行：评估拆分
- 函数超过 50 行：评估拆分
- 包含许多公共方法的服务：考虑按用例拆分服务

TypeScript/React：

- 文件超过 500 行：评估拆分
- hook 超过 150 行：评估拆分
- 生成的客户端文件如果保持隔离，可以超过这些限制

按职责拆分，而不是按任意行数拆分。

## 测试策略

重要行为需要保护时增加聚焦测试，但不要在普通小改动后例行执行测试。测试执行会消耗时间和基础设施，应保留在有意义的验证节点。

在以下关键时刻运行测试：

- 共享运行时、数据库 schema、并发、幂等性或跨模块契约发生变化；
- 修复生产事故和其他容易回归的可靠性工作；
- 完成一个重要功能切片；
- 发布、部署批次或改变生产行为的合并前；
- 静态检查无法证明正确性时。

对于小型文档、文案、样式或范围明确的机械式代码变更，默认只做 diff 评审和相关静态检查。不要仅因为文件发生变化就运行测试套件。需要测试时，先运行最小受影响集合；完整回归和实时模型测试保留给发布级或广泛/高风险变更。

使用基于切片的测试设计，不要求每个小片段都严格采用测试先行开发。

默认节奏：

```text
design a small vertical slice
  -> implement domain/schema/service code
  -> add deterministic tests for that slice
  -> add API/tool tests when the boundary exists
  -> add a small number of agent-flow tests after tool behavior is stable
```

优先顺序：

1. 领域和策略单元测试
2. 针对 PostgreSQL 的 repository 测试
3. 不调用 LLM 的确定性工具测试
4. API 测试
5. Worker/Run 状态测试
6. 少量 Agent 流程测试
7. 关键流程的前端交互测试

依赖 LLM 的测试应当受限，并且在普通本地运行中可选。大多数正确性应在不调用模型的情况下覆盖。

浏览器发布门禁使用 Playwright 覆盖关键用户旅程：身份认证和 Thread 创建、多项目 SSE 渲染、刷新和活动 Run 恢复、乐观编辑加撤销，以及澄清恢复。浏览器测试让真实 Next.js UI 对确定性的有状态 API 和 SSE 契约 fixture 运行。语音交互通过测试 MediaRecorder 使用固定音频字节；不得要求麦克风硬件或权限。真实后端语义仍由 PostgreSQL API/服务测试覆盖，实时模型质量则通过 Agent Eval 衡量。

FastAPI OpenAPI 是 HTTP schema 的事实来源。CI 在 API 作业中导出它，并在 Web 作业中检查已提交的 `schema.d.ts`。类型化端点使用 `openapi-fetch`，服务器提供的查询状态使用 TanStack Query；不要使用组件本地状态重建端点参数类型或分页缓存。SSE 不是 OpenAPI 请求/响应形状，因此在传输边界校验其 JSON，并且只将校验后的结果归约为可区分的 `RunEvent` 联合。

当被测行为是路由、预算、日志或状态映射时，应用编排单元测试可以使用数据库会话、模型调用器和提供商 gateway 的 fake。Repository 测试、API 持久化测试和工具测试仍必须针对 PostgreSQL 运行，因为 PostgreSQL 是事实来源，其约束、JSONB 行为、时间戳和事务行为都是产品契约的一部分。

对 Dayboard，在推进很远之前验证已完成的重要切片；不要把每个增量编辑都变成测试执行节点。

## 依赖决策

对于长期塑造项目的决策，使用 ADR：

- 框架选择
- 数据库选择
- 队列选择
- UI 系统选择
- ASR 提供商选择
- 身份认证提供商选择
- 日历组件选择
- 重要的 `north` 集成决策

小型实现依赖可以记录在 PR 或提交消息中，无需完整 ADR。
