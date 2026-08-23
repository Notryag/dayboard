# ADR-005 已认证身份边界

## 状态

当前预发布 schema 已由 [ADR-010](./010-user-scoped-identity.md) 取代。

## 背景

Dayboard 在所有产品服务和 repository 中传递 `TenantContext`，但当前 FastAPI dependency 始终返回一个
已配置的开发租户和用户。这对 Phase 1 prototype 有用，但对外部用户不安全：每个浏览器共享同一身份。

首个 beta 只需要可靠的注册和登录。在产品需要社交登录之前，增加独立的 Node authentication service
或依赖海外 identity control plane，会增加部署和中国网络风险。

## 决策

在 FastAPI service 内实现首个身份流程：

- username 和可选 email 注册；
- Argon2id password hashes；
- 不透明且可撤销的 server-side sessions；
- `HttpOnly` session cookie，其原始 token 永不存储在 PostgreSQL 中；
- 由 Dayboard 拥有的 users、profiles、tenants 和 memberships。

每个随机 session token 仅存储其 SHA-256 digest。Logout 会撤销 server-side session。Password hashes、
raw passwords、raw session tokens 和 cookie values 绝不能写入日志。

保留一个 provider-neutral external identity table，以便未来接入 WeChat、OIDC 或其他中国托管 provider。
External providers 是接入同一 Dayboard user 和 membership resolver 的 adapters；它们不会取代 Dayboard
所有权记录。

API authentication adapter 验证凭据，并返回包含以下内容的可信 claims：

```text
issuer
subject
email or phone when verified and available
display name when available
```

然后 Dayboard 通过自身的 user 和 tenant-membership records 解析这些 claims。只有该 resolver 会构造
`TenantContext`：

```text
verified password session or external identity
  -> Dayboard user
  -> active tenant membership
  -> trusted scheduling timezone and user locale
  -> TenantContext
```

调度 timezone 当前由 server 配置为 `Asia/Shanghai`。浏览器提供和模型提供的 timezone 均不可信。
`TenantContext.timezone` 仍是未来租户拥有的设置的边界。

Provider tokens、organization claims、request headers 和 model output 永远不会直接提供 Dayboard 的
`tenant_id`、`user_id`、timezone、roles 或 permissions。

未来的 authentication adapters 可以支持 WeChat、OIDC/JWT 或中国托管的 managed identity service。
Provider SDK types 保留在 `dayboard.integrations.identity` 内。Repositories、scheduling tools、North
和 domain schemas 只依赖可信的 Dayboard IDs 与 `TenantContext`。

允许两种明确的 runtime modes：

- `development`：用于本地开发和受控演示的一个已配置身份；
- `password`：经过验证的 server-side session，加上 Dayboard user/membership resolution。

Production 在 `password` mode 下运行，并拒绝不安全的 password cookies。Development mode 仅用于本地
开发或受控演示；它不是外部用户模式。

## 授权规则

- Authentication 证明账户身份；Dayboard membership 决定租户访问权限。
- 每个产品查询继续包含租户和所有者范围。
- Thread 和 Run streaming 需要与普通读取相同的所有权检查。
- Username 和 normalized email 对 password login 必须唯一。
- External subject 在其 issuer 内唯一，而不是仅按 subject string 全局唯一。
- User timezone 和 locale 来自 Dayboard profile，而不是不可信的 request claims。
- Service-to-service 和 scheduled executions 使用单独认证的 internal identities，而不是通过用户提供的
  header 绕过认证。
- Development identity headers 绝不能成为 production authentication mechanism。

## 后果

Dayboard 可以交付不依赖中国网络的首次登录，而无需将业务代码耦合到某个 provider。未来增加 WeChat
时，只需将 external identity 关联到同一用户，而不必重写 scheduling services。

Authentication 不能作为仅后端的开关完成：web client 需要在同一发布里程碑中支持 login、session refresh、
logout 以及 authenticated API/SSE requests。
