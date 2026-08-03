export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId: string | null,
    readonly code: string,
    readonly details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const authenticationRequiredEvent = "dayboard:authentication-required";

type ApiErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: unknown;
  };
};

const errorMessageKeys: Record<string, string> = {
  AUTHENTICATION_REQUIRED: "errors.authRequired",
  INVALID_CREDENTIALS: "errors.invalidCredentials",
  IDENTIFIER_ALREADY_REGISTERED: "errors.alreadyRegistered",
  INTERNAL_SERVER_ERROR: "errors.internal",
  THREAD_NOT_FOUND: "errors.threadNotFound",
  RUN_NOT_FOUND: "errors.runNotFound",
  COMMAND_ALREADY_IN_PROGRESS: "errors.commandInProgress",
  IDEMPOTENCY_CONFLICT: "errors.idempotencyConflict",
  CLARIFICATION_CONFLICT: "errors.clarificationConflict",
  CALENDAR_ENTRY_NOT_FOUND: "errors.calendarNotFound",
  TASK_ITEM_NOT_FOUND: "errors.taskNotFound",
  SCHEDULE_ITEM_CONFLICT: "errors.scheduleConflict",
  REMINDER_NOT_FOUND: "errors.reminderNotFound",
  REMINDER_STATE_CONFLICT: "errors.reminderConflict",
  COMMAND_QUEUE_UNAVAILABLE: "errors.queueUnavailable",
  RATE_LIMIT_EXCEEDED: "errors.rateLimit",
  VALIDATION_ERROR: "errors.validation",
  VOICE_EMPTY: "errors.voiceEmpty",
  VOICE_FORMAT_UNSUPPORTED: "errors.voiceFormat",
  VOICE_INVALID_AUDIO: "errors.voiceInvalid",
  VOICE_TOO_LARGE: "errors.voiceLarge",
  VOICE_TOO_LONG: "errors.voiceLong",
  VOICE_TOO_SHORT: "errors.voiceShort",
  VOICE_TRANSCRIPTION_FAILED: "errors.voiceTranscription",
  VOICE_UNAVAILABLE: "errors.voiceUnavailable",
  VOICE_VALIDATION_UNAVAILABLE: "errors.voiceValidation",
};

export function apiBaseUrl() {
  return process.env.NEXT_PUBLIC_DAYBOARD_API_BASE_URL ?? "http://127.0.0.1:8000";
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new Event(authenticationRequiredEvent));
  }
  let body: ApiErrorEnvelope = {};
  try {
    body = (await response.clone().json()) as ApiErrorEnvelope;
  } catch {
    // Non-JSON proxy errors still retain their status and request ID.
  }
  const error = body.error;
  return new ApiError(
    error?.message ?? `API request failed with ${response.status}`,
    response.status,
    error?.request_id ?? response.headers.get("x-request-id"),
    error?.code ?? `HTTP_${response.status}`,
    error?.details,
  );
}

export function userFacingApiError(error: unknown, fallback: string, locale: Locale = "zh-CN") {
  if (error instanceof ApiError) {
    const key = errorMessageKeys[error.code];
    const message = key ? getMessage(locale, key) : fallback;
    return error.requestId
      ? getMessage(locale, "errors.reference", { message, id: error.requestId })
      : message;
  }
  return fallback;
}
import { getMessage, type Locale } from "@/i18n";
