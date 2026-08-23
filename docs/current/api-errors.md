# API 错误契约

Dayboard API 错误对 HTTP 错误和请求校验失败使用同一种封装：

```json
{
  "error": {
    "code": "COMMAND_QUEUE_UNAVAILABLE",
    "message": "Command queue unavailable",
    "request_id": "req_0123456789abcdef",
    "details": {
      "run_id": "00000000-0000-0000-0000-000000000000"
    }
  }
}
```

- `code` 是客户端用于行为判断和翻译消息的稳定值。
- `message` 是安全的 API 描述，不是客户端应当用来匹配的值。
- `request_id` 用于将响应与服务器日志关联起来。
- `details` 是可选的结构化上下文，不得包含秘密或私有命令文本。

当前产品错误码：

| 错误码 | HTTP 状态 | 含义 |
| --- | ---: | --- |
| `AUTHENTICATION_REQUIRED` | 401 | 需要有效会话。 |
| `INVALID_CREDENTIALS` | 401 | 登录凭据被拒绝。 |
| `IDENTIFIER_ALREADY_REGISTERED` | 409 | 用户名或邮箱已注册。 |
| `THREAD_NOT_FOUND` | 404 | 当前所有者不存在该会话。 |
| `RUN_NOT_FOUND` | 404 | 当前用户范围内不存在该 Run。 |
| `COMMAND_ALREADY_IN_PROGRESS` | 409 | 该会话已有活动 Run。 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一个幂等键被用于不同输入。 |
| `CLARIFICATION_CONFLICT` | 409 | 澄清状态已过期或不再有效。 |
| `CALENDAR_ENTRY_NOT_FOUND` | 404 | 当前所有者不存在该日历条目。 |
| `TASK_ITEM_NOT_FOUND` | 404 | 当前所有者不存在该任务。 |
| `SCHEDULE_ITEM_CONFLICT` | 409 | 客户端加载后该调度项已发生变化。 |
| `COMMAND_QUEUE_UNAVAILABLE` | 503 | Run 已持久化，但无法排队。 |
| `RATE_LIMIT_EXCEEDED` | 429 | 超出该端点的请求限制。 |
| `VOICE_UNAVAILABLE` | 503 | 未配置语音识别提供商。 |
| `VOICE_FORMAT_UNSUPPORTED` | 415 | 不支持上传音频的 MIME 类型。 |
| `VOICE_EMPTY` | 422 | 上传内容不包含音频字节。 |
| `VOICE_INVALID_AUDIO` | 422 | 无法解码音频元数据。 |
| `VOICE_TOO_SHORT` | 422 | 录音短于接受的最小长度。 |
| `VOICE_TOO_LONG` | 413 | 解码后的时长超过配置限制。 |
| `VOICE_TOO_LARGE` | 413 | 上传内容超过配置的字节限制。 |
| `VOICE_VALIDATION_UNAVAILABLE` | 503 | 服务端音频检查不可用。 |
| `VOICE_TRANSCRIPTION_FAILED` | 502 | ASR 提供商未返回转写文本。 |
| `VALIDATION_ERROR` | 422 | FastAPI/Pydantic 请求校验失败。 |
| `INTERNAL_SERVER_ERROR` | 500 | 未预期的服务器错误已被安全封装。 |

其他 `HTTPException` 响应在获得产品专用错误码前使用 `HTTP_<status>`。当协议行为依赖状态码时，例如 HTTP 401 的会话恢复，Web 客户端必须保留基于状态码的处理；面向用户的消息则使用 `code`。

未知异常会在服务器端记录其类型、请求上下文和 traceback。异常消息和堆栈绝不会返回客户端。处理程序不会将请求正文或原始命令文本加入日志。
