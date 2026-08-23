# 当前 Agent 文档

本目录是 Dayboard Agent 行为的规范入口。这里记录产品的 Agent 规范；North 运行时内部实现和可复用的 Agent Platform 生命周期规范仍由各自所属的软件包维护。

只阅读任务所需的部分：

- [behavior-contract.md](./behavior-contract.md)：分类、澄清、搜索、写入、恢复和终止行为。
- [tools.md](./tools.md)：模型可见的 schema、可信字段排除、紧凑回执、工件和动态绑定。
- [context-memory.md](./context-memory.md)：运行时上下文、压缩、呈现工件和跨轮次锚点。
- [evaluation.md](./evaluation.md)：确定性检查、已部署验收、实时模型 Eval、权威 Oracle 和发布门禁。
- [../run-lifecycle.md](../run-lifecycle.md)：Run 状态、持久化交互、流排序、取消和恢复。
- [../architecture.md](../architecture.md)：North、Agent Platform、Dayboard、存储和部署所有权。
- [../time-protocol.md](../time-protocol.md)：模型本地时间、UTC 存储、呈现隔离和行版本并发。

## 文档边界

提示词是行为规范的实现，而不是唯一规范。持久化业务规则仍由产品代码、工具规范和测试承载。行为变更必须在同一变更中更新最窄范围的当前文档，以及对应的确定性测试或版本化 Eval 用例。

不要将 North 或 Agent Platform 的内部实现复制到本目录。应链接到所属规范，并在 ADR 中记录跨包决策。历史测量结果和已完成的实现计划属于 `docs/records/` 和 `docs/archive/`。
