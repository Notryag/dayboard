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
| `VALIDATION_ERROR` | 422 | FastAPI/Pydantic request validation failed. |

Other `HTTPException` responses use `HTTP_<status>` until they receive a product-specific code.
The web client must retain status-based handling where protocol behavior depends on it, such as
session recovery on HTTP 401, and use `code` for user-facing messages.
