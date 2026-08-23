# 当前路线图

最后审阅：2026-08-23

本文件只包含未完成的工作。已完成的发布事实属于
[`PROJECT_STATE.md`](../PROJECT_STATE.md)，实现测量在 `docs/records/`，已完成或已取代的计划在 `docs/archive/`。

## Agent 运行时与 Eval

- [ ] 移除 `ask_clarification` 后 North 多余的一轮模型调用；在
  [north-agent#1](https://github.com/Notryag/north-agent/issues/1) 中跟踪。v0.3.25 澄清 Run
  中跟踪运行时修复。v0.3.25 澄清 Run 通过三次调用使用了 11,304 个 token，其中多余的最后一次调用使用 3,981 个 token。
- [ ] 只有在 OpenAI 兼容 gateway 证明具备该能力，或产品规模超出现有内聚调度工具集时，才重新评估提供商原生的延迟工具加载。单独的 skill 不会移除可执行 schema，而基于模型的选择器会增加一次调用。

当前行为和门禁位于
[`current/agent/`](../current/agent/README.md)；测量的 token 历史位于
[`records/agent-token-optimization-history.md`](../records/agent-token-optimization-history.md)。

## Gateway 预算所有权

Northgate 前置条件：[northgate#3](https://github.com/Notryag/northgate/issues/3) 跟踪可信的租户/用户归属和范围化策略执行。其当前 gateway 全局策略只是全局成本保护，不是 Dayboard 用户预算的替代品。

- [ ] 为 Northgate 添加签名且可信的动态租户和用户归属。仅有相关元数据绝不能授权策略范围。
- [ ] 为已认证元数据维度添加 Northgate 策略范围，至少包括 gateway、租户、用户和模型。策略必须具有明确优先级，以及原子预留/结算。
- [ ] 通过 Northgate 运维 API 暴露范围化用量、拒绝原因、剩余额度和重置时间，但不记录提示词内容。
- [ ] 将 Dayboard 所有生产模型流量经由 Northgate 路由，并在转移执行权之前移除直接提供商回退。
- [ ] 范围化 Northgate 策略通过集成和失败路径测试后，删除 Dayboard 的提供商 token `ProviderBudgetGuard`、Redis 计数器和重复预算配置。
- [ ] 保留 Dayboard 对命令频率、身份认证、音频和其他产品端点的应用滥用限制；这些不是提供商预算策略。
- [ ] 迁移期间删除已取代路径，而不是保留兼容层。

## 有条件的平台抽取

这些事项有意等待真实复用证据，而不是等待实现能力：

- [ ] 只有第二个产品证明使用相同的 schema、身份、事务和生命周期契约后，才重新评估可选的 Agent Platform SQLAlchemy 适配器。
- [ ] 只有第二个产品证明存在通用运行时契约后，才泛化 North 适配器；Agent Platform 当前不得导入 North。
- [ ] 只有第二个产品需要相同的稳定生命周期边界后，才评估将提供商用量计量或通知投递作为 Platform 能力。

已完成的抽取计划保存在
[`archive/agent-platform-extraction.md`](../archive/agent-platform-extraction.md)。ADR-008 和
ADR-009 仍是决策权威。

## 延后的后台通知

- [ ] 只有用户需要在 Dayboard 关闭时收到提醒，才重新考虑已安装 PWA 的后台 Web Push。该功能需要 Service Worker、VAPID 凭据、加密设备订阅、每设备投递尝试、重试/清理以及通知点击导航。

在该触发条件出现前，Dayboard 保留已认证的提醒中心，以及应用活动时可选的前台浏览器 Notification；不得将其表示为后台投递。
