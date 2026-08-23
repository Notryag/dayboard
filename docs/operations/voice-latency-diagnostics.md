# 语音延迟诊断

Dayboard 会为每次接受的按住手势尽力记录一条结构化启动测量。浏览器不会向此端点提交音频、转写、提示词或凭据。PostgreSQL 不保存这些测量；API 将 `dayboard.voice.startup_measured` 写入结构化日志。

## 启动耗时拆解

| 字段 | 含义 |
| --- | --- |
| `press_to_request_ms` | 指针/按键按下处理程序到调用 `getUserMedia()` |
| `get_user_media_ms` | 浏览器和操作系统获取麦克风 |
| `stream_to_recorder_ready_ms` | 获取流到配置的 `MediaRecorder` 就绪 |
| `recorder_start_call_ms` | 同步调用 `MediaRecorder.start()` |
| `press_to_recording_ms` | 从按下到录音器启动的完整路径 |
| `press_to_cancel_ms` | 适用时，在录音器启动前释放/取消所需时间 |

每条记录还包含随机测量 ID、发布标签、结果、已认证用户 ID 和受限的 User-Agent。结果为 `recording`、`cancelled` 或 `failed`。缺失阶段报告为 `null`，绝不会是零。

检查生产样本时，不要无限跟踪日志：

```bash
docker compose -f docker-compose.yml -f docker-compose.platform.yml \
  logs --no-log-prefix --since=30m api \
  | jq -c 'select(.event == "dayboard.voice.startup_measured")'
```

页面加载后至少测量十次首次按下样本，并在同一手机上立即重复按下十次。按精确发布版本和 User-Agent 比较：

- `press_to_request_ms` 较高说明应用手势处理耗时；
- `get_user_media_ms` 较高说明浏览器、权限或硬件冷启动耗时；
- `stream_to_recorder_ready_ms` 较高说明格式选择或录音器构造耗时；
- `recorder_start_call_ms` 较高说明浏览器录音器实现耗时。

在生产样本建立可复现基线前不要引入阈值。WebSocket ASR 准备影响从释放到转写的延迟，而不是 `get_user_media_ms`；当获取麦克风是主要阶段时，应实验短时流预热或原生录音桥接。
