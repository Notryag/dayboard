# 当前文档

这些文档是已实现产品的规范描述：

- [architecture.md](./architecture.md)：系统边界、基础设施、持久化、前端和部署形态。
- [module-map.md](./module-map.md)：代码位置、依赖权限、公共模块契约、事务归属和跨模块不变量。
- [product-model.md](./product-model.md)：面向用户的概念和调度语义。
- [identity-model.md](./identity-model.md)：已认证用户的所有权、隔离以及 HTTP/Worker 身份边界。
- [run-lifecycle.md](./run-lifecycle.md)：排队执行、Redis Stream/SSE 投递、持久化、恢复、澄清、取消和用量。
- [time-protocol.md](./time-protocol.md)：北京时间本地模型协议、UTC 持久化、工件隔离和行版本并发。
- [agent/README.md](./agent/README.md)：Agent 行为、工具、上下文/记忆、评估，以及 Run/运行时契约链接。
- [ui-design.md](./ui-design.md)：已实现的视觉、交互、令牌、布局和组件规则。
- [api-errors.md](./api-errors.md)：稳定的 HTTP 错误封装。

实现改变契约时，必须在同一变更中更新相应文件。不要在这里放置历史决策依据或里程碑检查清单；分别使用 ADR 和归档目录。

后端实现请先阅读 `architecture.md`，再阅读 `module-map.md`。Agent 工作请从 `agent/README.md` 路由；涉及 Run、流或澄清的变更继续阅读 `run-lifecycle.md`。任务未跨越这些边界时，不要阅读所有当前文档。
