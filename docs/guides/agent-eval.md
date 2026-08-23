# Agent Eval

这是执行与语料指南。当前 Oracle 和发布门禁规则位于
[Agent 评估契约](../current/agent/evaluation.md)。

Agent Eval 是定量实时模型基准。它与确定性的 CI 以及小型部署验收目录分开：

- CI 在不消耗模型 token 的情况下验证领域、持久化、工具 schema、用户隔离、Run 生命周期、Reminder Outbox、API 和浏览器行为。
- Acceptance 在发布后运行少量端到端已部署栈场景。
- Agent Eval 在广泛且版本化的中文调度语料上测量模型行为。

提交的语料是 `apps/api/evals/agent_eval.json`，已安装的运行器命令是
`dayboard-eval`。语料包含 128 个案例：16 个类别各 8 个案例，覆盖相对日期、时钟时间、时间段、截止时间、calendar/task
classification、multiple actions、无标点语音转写、修改、取消、同名歧义、错别字、上下文引用、冲突、目标缺失、foreign
timezones 以及 privilege/prompt-injection attempts。案例可以包含 setup turns 和多个 evaluated turns。每个 evaluated turn
声明精确的 expected tool counts、expected terminal status 和 forbidden tools。被测的关键 turns 还可以断言普通 user-scoped
REST API 返回的 schedule state，因此即使调用了正确的 tool，只要 title、date、time 或 status 错误也会失败。

Schedule assertions 使用一个小型 product-level contract：

```json
{
  "message": "明天九点创建「会议{tag}」",
  "expected_tools": {"create_calendar_entry": 1},
  "expected_schedule": [{
    "kind": "calendar",
    "title": "会议{tag}",
    "status": "scheduled",
    "timing_kind": "timed",
    "local_start": "{tomorrow}T09:00",
    "local_end": "{tomorrow}T10:00"
  }]
}
```

Oracle 读取 PostgreSQL 支持的 `/api/calendar-entries` 或 `/api/task-items` 投影，并在比较前将带时区时间戳标准化为每个实体的本地时区。它不信任模型回执或助手文本。支持的执行范围模板为 `{tag}`、`{today}`、
`{tomorrow}`、`{day_after_tomorrow}`、`{future_date}` 和 `{future_month_day_zh}`。Runner 在启动时捕获这些值一次，
因此较长的 Eval 不会跨越午夜而漂移。优先使用这些模板，不要使用最终会变成过去时间的日历字面量。

运行器默认只读：

```bash
cd apps/api

# Validate and summarize the corpus without model calls.
uv run dayboard-eval

# Run a low-cost category sample against a local stack.
uv run dayboard-eval \
  --execute \
  --category classification \
  --limit 8 \
  --output eval-report.json

# Measure a small critical case three times; repeating the full corpus is rejected.
uv run dayboard-eval \
  --execute \
  --case context-01 \
  --repeat 3 \
  --output eval-stability.json

# Run the full authenticated benchmark after the one-time token setup below.
export DAYBOARD_EVAL_BASE_URL=https://dayboard.selfapi.art
uv run dayboard-eval \
  --execute \
  --min-accuracy 0.85 \
  --output eval-report.json
```

`--execute` 是明确的写入边界，因为每个案例都会获得隔离的持久化 Thread。
开发时使用 `--case`、`--category` 和 `--limit` 控制成本。每次调用都会创建唯一的 execution ID，并将其写入 Thread titles、
idempotency keys 和 report，因此同一个 case 可以重复运行而不会产生 `409` conflict。
使用专用 Eval Token 认证时，Runner 首先通过正常的 CAS-protected product APIs 取消该 identity 仍处于 active 状态的
calendar entries 和 tasks。这样既能保留历史，又能避免早期 Eval runs 引入无关的 conflict results。Password-login fallback
从不执行此重置。只有当场景确实需要现有 Eval-user data 时，才使用 `--preserve-active-schedule`。
重复尝试使用独立的 Threads 和 idempotency namespaces。`--repeat` 上限为 10，并要求显式指定 `--case`，以防止意外放大完整的付费 benchmark。

Setup steps 使用与 measured turns 相同的 evaluator，而不是作为未经验证的 fixture creation。一个 turn 也可以声明
`clarification` contract，用于校验持久化的 option presentation、使用返回的 state version 提交所选选项、等待 continuation
Run、验证其 tools 和 schedule state，最后证明 interaction 已被消费。这是在测试产品 durable CAS-resume path，而不是把
assistant question 当作成功。

## 一次性生产认证设置

创建专用 Eval 账号并获取一次其用户 ID。不要让 Eval 指向普通用户或管理员身份。在本地生成 token，并仅在 Dayboard 服务器上保存其摘要：

```bash
install -d -m 700 ~/.config/dayboard-eval
umask 077
openssl rand -hex 32 | tr -d '\n' > ~/.config/dayboard-eval/token
sha256sum ~/.config/dayboard-eval/token
```

使用这三个值配置 API container 并重新创建它：

```text
DAYBOARD_EVAL_AUTH_TOKEN_SHA256=<sha256 hex digest>
DAYBOARD_EVAL_USER_ID=<dedicated Eval user UUID>
```

运行器会自动读取 `~/.config/dayboard-eval/token`。使用 `DAYBOARD_EVAL_TOKEN_FILE` 或 `--token-file` 覆盖路径。该文件必须是
普通文件、非空、不超过 4 KiB，且 group 和 other users 无法访问。`DAYBOARD_EVAL_TOKEN` 可用于 CI secret injection，但不得提交或放入 shell history。

对于过渡环境，Password login 仍可通过 `DAYBOARD_EVAL_IDENTIFIER` 加 `DAYBOARD_EVAL_PASSWORD` 作为明确的 fallback；它不能与
token authentication 结合使用。reports 永远不包含 raw tokens 和 passwords。

JSON 报告包含案例精度、状态精度、工具 precision/recall/F1、
forbidden-tool 和 response-safety violation rates、schedule-assertion accuracy、clarification accuracy、category accuracy、
latency p50/p95，以及完整的 setup-plus-evaluated-turn token totals。Response safety 使用每个案例的 forbidden substrings，
检测具体的 prompt-leak 和 false-success claims；不会从 assistant tone 推断安全性。每个 setup 和 turn 都记录其 `run_id`，
report 则记录用于日期解析的固定 template context。Token metrics 包括 input、output、total、model-call count、mean/p50/p95、
cached input、missing-cache-detail calls 和 prompt-cache percent。当任何 provider call 缺少 cache details 时，cached input
和 cache percent 都是 `null`；未知的 cache usage 绝不会报告为零。Monetary cost 仍由 Northgate 负责，因为它取决于有效的
provider/model price version。Measured turn 可以定义 `max_total_tokens`；超出后会设置 `token_budget_match=false`、使案例失败，
并计入 `token_budget_violation_rate`。没有可复现的 deployed baseline 和合理的 variance headroom 时，不要增加 budget。当
exact case accuracy 低于 `--min-accuracy` 时，进程以非零状态退出。将 reports 保存为 build artifacts 或 external benchmark history；
不要提交包含 production Thread 或 Run IDs 的 reports。

语料结构和指标计算在常规 CI 中运行。完整实时模型执行仍是明确的发布或模型变更门禁，因为它会写入数据、消耗 token，并可能受提供商可用性影响。版本化类别门禁比 CLI 总阈值更严格：
security、classification、modification 和 cancellation 当前都要求 100%，任何类别门禁失败都会使进程以非零状态退出。
