# ADR-006 租户隔离与外部工具边界

## 状态

当前预发布 schema 已由 [ADR-010](./010-user-scoped-identity.md) 取代。

## 背景

Dayboard 在一个 PostgreSQL 数据库中存储多个用户和租户。Scheduling、conversation、Run、reminder、
voice 和 provider-usage records 都是产品数据，绝不能跨越已认证的租户或所有者边界。

North 执行工具，但不拥有 Dayboard 身份或授权。未来的外部工具（包括 private knowledge search）可能
调用 Dayboard 进程之外的服务。允许模型或浏览器向这些工具提供身份字段，会使提示词输出变成授权决策。

DeerFlow 2.0 提供了有用的所有者隔离模式，尤其是 fail-closed repository access、可信 runtime identity
和 user-scoped files。Dayboard 保留其明确的租户模型，而不是复制 DeerFlow 的 user-only context、
default-user fallback、Gateway 或 authorization stack。

## 决策

采用应用强制的共享数据库隔离：

- authentication 和 active membership 生成不可变的 `TenantContext`；
- product services 和 repositories 显式要求该 context；
- owner-scoped rows 同时携带 `tenant_id` 和 `owner_user_id`；
- reads、writes、streams、cancellation、usage records 和 background work 使用相同的范围；
- production 不存在未认证的 default identity；
- dedicated schemas 或 databases 仍是未来的部署选项，而不是独立的 service APIs。

Agent 和 external tool schemas 仅包含由模型控制的业务输入。以下内容属于可信 server context，必须在
authentication 后注入：

```text
tenant_id, user_id, owner_user_id, timezone, locale,
run_id, thread_id, request_id, permissions
```

Dayboard 在组装 Agent 时验证这条规则。任何将这些名称之一暴露给模型的工具，都会在调用前被拒绝。

External tools 仍是普通的注入式 LangChain/North tools。例如，未来的 knowledge search tool 接收
`query`、`limit` 和业务过滤条件，而其 closure 或 service object 持有经过认证的 `TenantContext`、
database session、credentials 和 authorization policy。North 不增加产品 RAG abstraction，也不存储
Dayboard embeddings。

Redis jobs 仅携带 `run_id`。Workers 从持久化的 Dayboard Run 及其经过认证的所有权记录中恢复身份和输入
文本。Queue metadata 和 model arguments 不是独立的权威来源。租户范围内的文件和未来的 document chunks
使用相同的可信租户和所有者标识符。

Tenant switching、shared calendars 和 role permissions 推迟到一个账户可以主动操作多个租户之后再实现。
届时，选定的租户必须存储在可信 session 或 request credential 中，并针对 active membership 进行检查。
现有 membership 的 `role` 字段本身不构成授权。

## 后果

增加业务工具或外部工具需要显式的 server-side context binding。每个新 repository 以及外部可访问的
Run 或文件操作仍必须包含跨租户测试。

这种方式不提供 PostgreSQL row-level security。缺失 repository predicate 仍然是应用缺陷，因此 repository
APIs 必须继续要求 `TenantContext` 并 fail closed。如果企业部署需要数据库强制隔离，未来可以将 PostgreSQL
RLS 作为 defense in depth 纳入考虑。

在产品拥有 shared-tenant workflows 之前，Dayboard 避免引入通用 Principal/RBAC framework，同时保留在
应用边界增加该框架的清晰路径。
