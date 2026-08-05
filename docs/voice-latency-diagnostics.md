# Voice Latency Diagnostics

Dayboard records one best-effort structured startup measurement for each accepted hold gesture.
The browser submits no audio, transcript, prompt, or credential to this endpoint. PostgreSQL does
not store these measurements; the API emits `dayboard.voice.startup_measured` to structured logs.

## Startup Breakdown

| Field | Meaning |
| --- | --- |
| `press_to_request_ms` | Pointer/key press handler to the `getUserMedia()` call |
| `get_user_media_ms` | Browser and operating-system microphone acquisition |
| `stream_to_recorder_ready_ms` | Stream acquisition to configured `MediaRecorder` readiness |
| `recorder_start_call_ms` | Synchronous `MediaRecorder.start()` call |
| `press_to_recording_ms` | Complete press-to-recorder-start path |
| `press_to_cancel_ms` | Time to release/cancel before recorder startup, when applicable |

Every record also contains a random measurement ID, release tag, outcome, authenticated user ID,
and bounded User-Agent. Outcomes are `recording`, `cancelled`, or `failed`. Missing stages are
reported as `null`, never zero.

Inspect production samples without following the log indefinitely:

```bash
docker compose -f docker-compose.yml -f docker-compose.platform.yml \
  logs --no-log-prefix --since=30m api \
  | jq -c 'select(.event == "dayboard.voice.startup_measured")'
```

Measure at least ten first-press samples after a page load and ten immediately repeated presses on
the same phone. Compare by exact release and User-Agent:

- high `press_to_request_ms` points to application gesture work;
- high `get_user_media_ms` is browser, permission, or hardware cold start;
- high `stream_to_recorder_ready_ms` points to format selection or recorder construction;
- high `recorder_start_call_ms` points to the browser recorder implementation.

Do not introduce thresholds until production samples establish a reproducible baseline. WebSocket
ASR preparation affects release-to-transcript latency, not `get_user_media_ms`; short-lived stream
warming or a native recording bridge is the relevant experiment when microphone acquisition is the
dominant stage.
