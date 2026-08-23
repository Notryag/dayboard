# ADR-008 引入 Agent 应用平台层

## 状态

已接受。原始的严格依赖链图已由 [ADR-009](./009-keep-platform-and-north-independent.md) 取代；所有权决策仍然有效。

## 背景

Dayboard 当前有两个架构层：

```text
North runtime <- Dayboard product
```

这使调度概念不会进入 North，但 Dayboard 现在还包含一些并非调度专属的应用能力：已认证身份上下文、对话、Runs、持久化消息历史、工件恢复、澄清、媒体输入、提醒交付基础设施以及提供商用量核算。

未来的产品（例如营养或锻炼记录器）需要其中许多能力，但不应依赖 Dayboard 的日历、任务、提示词、工具或呈现模型。复制这些能力会使修复和运维行为分散到多个产品中。将它们移入 North 会让 runtime 了解应用策略和持久化，从而反转使 North 保持可复用的依赖方向。

## 决策

> 下图记录了原始的所有权决策。其中严格的 Platform-to-North 导入链接已由 [ADR-009](./009-keep-platform-and-north-independent.md) 取代。

引入第三个可独立安装的层：

```text
North <- Agent Application Platform <- Dayboard
                                   <- future products
```

原始提案将箭头视为导入依赖：`Dayboard -> Agent Application Platform -> North`。这一严格方向已不再是当前规则；ADR-009 保留了禁止向上导入的规则，同时让 North 和 Platform 成为彼此独立的底层依赖。runtime 调用和数据可以通过声明的接口双向流动，而不会反转源代码依赖。

### North 负责 runtime 原语

North 负责与产品无关的模型调用、Agent 循环、中间件执行、检查点、规范 runtime 事件、Run 执行机制、流桥和 runtime 压缩时机。它不负责用户、租户、HTTP API、产品对话、产品提醒或领域工件。

### Agent 应用平台负责可复用的应用能力

平台层负责对多个对话产品都有价值的契约和用例：

- 可信的租户和用户上下文；
- 对话线程、基于游标分页的消息和持久化历史；
- 产品 Run 记录、幂等命令提交、恢复、取消和状态映射；
- 类型化消息工件和刷新恢复；
- 澄清及其他可恢复的用户交互；
- 媒体摄取边界；
- 通知交付基础设施；
- 提供商用量和预算记录。

平台不决定日历条目、任务、餐食、卡路里、锻炼或产品卡片的含义。可复用基础设施必须接受明确的产品适配器，而不是导入产品模块。

这三层描述的是逻辑所有权，而不是每层各对应一个扁平模块。平台内部划分为：

- `core`：不导入框架的 identity、Conversation、Run、Interaction 和错误契约；
- `application`：限定在事务范围内的用例和生命周期状态机；
- `ports`：存储、runtime 执行、事件发布和产品投影接口；
- `adapters`：实现这些 port 的可选 PostgreSQL 和 North 集成。

Adapters 向内依赖平台契约。Platform Core 和应用用例不依赖 SQLAlchemy、FastAPI、产品包或具体模型提供商。North adapter 可以依赖 North，但不得让 North 概念泄漏到与产品无关的契约中。

### Dayboard 负责调度产品语义

Dayboard 负责日历条目、作为调度策略的提醒、调度 repository 和 service、工具 schema、提示词、时间分类、调度回执、调度呈现部分以及 Dayboard UI。

Northgate 仍是用于测量和诊断的 sidecar。它不属于三层应用依赖链，也不得修改应用上下文。

## 一致性与扩展边界

平台用例负责自身的原子性要求。Run 转换及其持久化生命周期事件，或者幂等声明及由该声明创建的 Run/消息，必须作为一个单元一起提交或回滚。因此，存储 port 必须通过显式的 Unit of Work 组合；正确性不能依赖多个 repository 恰好共享一个未表达出来的 SQLAlchemy Session。

产品数据通过带版本的 envelope 穿过平台边界。平台负责 envelope 的身份、schema 版本、生命周期、持久化和重放。产品负责 payload 及其校验。这样，Dayboard 调度卡片和未来的营养产品可以使用同一条持久化管道，而无需引入通用领域 `Item`，也不会让无版本的 `dict[str, Any]` 变成永久协议。

可恢复交互使用乐观并发。平台负责源 Run 关联、过期、状态版本以及原子声明/解决行为。Dayboard 负责调度候选项、选项标签、本地时间投影以及根据所选选项生成的命令。

## 包边界

平台包位于 `packages/agent-platform`，导入名为 `agent_platform`。每个提取切片完成后，Dayboard 将通过公共包 API 使用它。`agent_platform` 导入 `dayboard` 是禁止的，CI 会对此进行检查。

North 在自己的 repository 中维护。North 不得导入 Dayboard 或平台的现有规则仍在那里执行。不得使用动态导入绕过任一边界。

依赖防护会逐步扩展，以覆盖平台 Core 的框架独立性和 Dayboard 的内部依赖方向。通过导入检查是必要条件，但并不充分：adapter 契约测试、事务回滚测试、乐观并发测试和租户隔离测试也必须覆盖组装后的生产路径。

在 runtime 迁移之前引入该包，是为了让所有权拥有真实的归属位置，并防止新的可复用代码继续积累在 Dayboard 内部。

## 提取策略

使用经过测试的垂直切片，而不是整体移动文件夹：

1. 建立包、所有权映射和依赖防护；
2. 连同所需的最小 identity 和 artifact 契约一起提取 Conversation + Run；
3. 让 Dayboard 切换到提取后的公共 API，并移除原始实现；
4. 在迁移更多编排之前，明确事务所有权、幂等性和与持久化无关的记录；
5. 提取带版本的呈现 envelope 和可恢复交互 envelope，并进行原子解决；
6. 将通用命令提交和 Run 协调从 Dayboard Agent 执行及结果投影中拆分出来；
7. 只有在产品适配器明确后，才提取媒体、用量和通知基础设施；
8. 将调度提醒、工具、提示词、领域模型和 UI 保留在 Dayboard 中。

对于尚未发布的内部导入，不设置兼容层。每个已完成的切片只有一个实现，并移除之前的路径。

## 被否决的替代方案

### 将所有可复用行为放入 North

否决原因是：身份验证、产品持久化、HTTP 策略和通知交付属于应用层关注点。North 会与一种部署模型耦合，并最终导入其消费者的概念。

### 构建通用 item 模型

否决原因是：日历、餐食、锻炼和未来产品具有不同的不变量。通用 JSON item 会把领域校验从数据库移到约定中。

### 为每个新产品复制 Dayboard

否决原因是：Run 恢复、对话历史、用量核算和安全修复会立即产生分歧。

### 执行一次性大规模提取

否决原因是：当前模块将可复用编排与调度策略混在一起。先移动文件只会在新的包名下保留错误的耦合。

## 后果

该架构获得了一个可复用的中间层，同时不会污染 North 或削弱产品领域模型。依赖违规会在 CI 中失败，提取工作可以一次完成一个完整工作流。

直接成本是增加一个包、明确的事务边界、带版本的扩展契约和 adapter 设计。在某个切片完成迁移之前，当前 Dayboard 实现仍是权威实现；目标所有权绝不会被描述成已经实现的平台功能。
