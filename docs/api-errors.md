# API Error Contract

Dayboard API errors use one envelope for HTTP errors and request validation failures:

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

- `code` is the stable value clients use for behavior and translated messages.
- `message` is a safe API description, not a value clients should match.
- `request_id` correlates the response with server logs.
- `details` is optional structured context and must not contain secrets or private command text.

Current product error codes:

| Code | HTTP status | Meaning |
| --- | ---: | --- |
| `AUTHENTICATION_REQUIRED` | 401 | A valid session is required. |
| `INVALID_CREDENTIALS` | 401 | Login credentials were rejected. |
| `IDENTIFIER_ALREADY_REGISTERED` | 409 | Username or email is already registered. |
| `THREAD_NOT_FOUND` | 404 | The conversation does not exist for the current owner. |
| `RUN_NOT_FOUND` | 404 | The Run does not exist for the current tenant. |
| `COMMAND_ALREADY_IN_PROGRESS` | 409 | The thread already has an active Run. |
| `IDEMPOTENCY_CONFLICT` | 409 | An idempotency key was reused for different input. |
| `CLARIFICATION_CONFLICT` | 409 | Clarification state is stale or no longer valid. |
| `COMMAND_QUEUE_UNAVAILABLE` | 503 | The Run was persisted but could not be queued. |
| `RATE_LIMIT_EXCEEDED` | 429 | The endpoint-specific request limit was exceeded. |
| `VOICE_UNAVAILABLE` | 503 | No speech recognition provider is configured. |
| `VOICE_FORMAT_UNSUPPORTED` | 415 | The uploaded audio MIME type is unsupported. |
| `VOICE_EMPTY` | 422 | The upload contains no audio bytes. |
| `VOICE_INVALID_AUDIO` | 422 | Audio metadata could not be decoded. |
| `VOICE_TOO_SHORT` | 422 | The recording is shorter than the accepted minimum. |
| `VOICE_TOO_LONG` | 413 | The decoded duration exceeds the configured limit. |
| `VOICE_TOO_LARGE` | 413 | The upload exceeds the configured byte limit. |
| `VOICE_VALIDATION_UNAVAILABLE` | 503 | Server-side audio inspection is unavailable. |
| `VOICE_TRANSCRIPTION_FAILED` | 502 | The ASR provider did not return a transcript. |
| `VALIDATION_ERROR` | 422 | FastAPI/Pydantic request validation failed. |
| `INTERNAL_SERVER_ERROR` | 500 | An unexpected server error was safely contained. |

Other `HTTPException` responses use `HTTP_<status>` until they receive a product-specific code.
The web client must retain status-based handling where protocol behavior depends on it, such as
session recovery on HTTP 401, and use `code` for user-facing messages.

Unknown exceptions are logged server-side with their type, request context, and traceback. Their
message and stack are never returned to the client. The handler does not add request bodies or raw
command text to logs.
