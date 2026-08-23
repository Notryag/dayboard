# 身份与数据范围

这是移除预发布租户后的已实现身份模型。

## 决策

Dayboard 当前是多用户个人调度应用，而不是工作区或组织产品。授权和持久化边界是已认证用户：

```text
UserContext(
  user_id,
  timezone,
  locale,
)
```

活动 schema 或应用契约中不存在 `Tenant`、`TenantMembership`、`tenant_id` 或 `owner_user_id`。所有用户所有的业务行都使用 `user_id`。Repository 要求显式传入 `UserContext`，并在每次用户范围的读取、写入、锁定和删除中包含 `user_id`。

这不妨碍未来构建共享产品。如果 Dayboard 增加共享日历、团队或工作区，应在那时引入真正的 `Workspace` 和成员模型。不要保留一个选择和授权语义尚不存在的占位租户抽象。

## 请求与 Worker 边界

HTTP 身份认证通过 FastAPI 依赖注入解析可信的 `UserContext`：

```text
session or Eval bearer identity
  -> UserRow + UserProfileRow
  -> UserContext
  -> service
  -> repository(user_id = context.user_id)
```

请求中间件只负责请求 ID 和结构化日志清理。它不会从调用方提供的 header 推断授权，用户范围也不会隐藏在全局 ORM 过滤器中。

Worker 保留一条单独且明确的恢复路径：

```text
Redis job(run_id)
  -> system-scoped Run lookup
  -> persisted Run.user_id
  -> UserContext
  -> user-scoped service and repositories
```

Redis 只携带 `run_id`，不是身份权威来源。Worker 绝不能从队列元数据或模型参数重建所有权。

## 数据库规则

- `users`、凭据、资料、会话和外部身份是全局账户记录。
- 会话、Run、幂等键、日程、提醒、语音转写和提供商用量记录在属于用户时携带 `user_id`。
- 如果子记录天然由全局唯一的 Run ID 限定，可以依靠 `run_id` 查询，但其父 Run 仍然是用户范围的。
- 只要唯一性规则是用户本地的，唯一约束就必须包含 `user_id`，例如幂等使用 `(user_id, key)`，提供商用量使用 `(user_id, run_id)`。
- 缺少用户谓词属于存储缺陷。应用服务不得先查询、之后才授权。
