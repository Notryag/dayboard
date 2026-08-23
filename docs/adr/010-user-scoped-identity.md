# ADR-010 在共享工作区出现前使用用户范围

## 状态

已接受

## 背景

Dayboard 当前提供个人日历、任务、提醒和 Agent 会话。它有用户和会话，但没有工作区切换器、成员权限、共享资源或组织边界。因此，之前的 Tenant 和 TenantMembership 表增加了 schema 和身份认证复杂性，却没有表示真实的产品能力。

## 决策

使用已认证用户作为应用隔离边界：

- 在 HTTP 边界解析不可变的 `UserContext(user_id, timezone, locale)`；
- 通过服务和 repository 显式传递 `UserContext`；
- 在用户所有的业务记录上存储 `user_id`，并将其纳入用户范围的唯一约束；
- Worker 在构建 `UserContext` 前从 PostgreSQL 加载 `Run.user_id`；
- Redis 作业中只放入 `run_id`；
- 等共享产品工作流出现后，再引入真正的 `Workspace` 和成员模型。

预发布 schema 已重置，初始 Alembic 迁移已重新生成。不保留兼容层或范围的双重表示。

## 后果

当前模型更小，并且只有一个明确的范围。它不声称支持多租户共享。Repository 过滤仍是应用层不变量；当前未启用 PostgreSQL 行级安全。

引入共享日历或团队时，应作为一次产品变更添加一等 Workspace、成员关系、选定工作区上下文和授权策略。不要仅为保留未使用的抽象而重新引入 Tenant 名称。
