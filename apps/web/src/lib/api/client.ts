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

const errorMessages: Record<string, string> = {
  AUTHENTICATION_REQUIRED: "登录状态已失效，请重新登录。",
  INVALID_CREDENTIALS: "账号或密码不正确。",
  IDENTIFIER_ALREADY_REGISTERED: "用户名或邮箱已被注册。",
  INTERNAL_SERVER_ERROR: "服务出现异常，请稍后重试。",
  THREAD_NOT_FOUND: "当前对话已不存在，请重新开始。",
  RUN_NOT_FOUND: "该请求已不存在，请重新提交。",
  COMMAND_ALREADY_IN_PROGRESS: "上一条请求仍在处理中，请稍候。",
  IDEMPOTENCY_CONFLICT: "请求标识已被其他操作使用，请重新提交。",
  CLARIFICATION_CONFLICT: "这个选项已经失效，请重新选择。",
  CALENDAR_ENTRY_NOT_FOUND: "这个日程已不存在。",
  TASK_ITEM_NOT_FOUND: "这个待办已不存在。",
  SCHEDULE_ITEM_CONFLICT: "安排已被更新，请刷新后重试。",
  REMINDER_NOT_FOUND: "这条提醒已不存在。",
  REMINDER_STATE_CONFLICT: "提醒状态已经变化，请刷新后重试。",
  COMMAND_QUEUE_UNAVAILABLE: "服务暂时繁忙，请稍后重试。",
  RATE_LIMIT_EXCEEDED: "操作过于频繁，请稍后再试。",
  VALIDATION_ERROR: "提交的信息不完整或格式不正确。",
  VOICE_EMPTY: "没有录到声音，请重新录制。",
  VOICE_FORMAT_UNSUPPORTED: "当前录音格式不受支持。",
  VOICE_INVALID_AUDIO: "录音文件无法读取，请重新录制。",
  VOICE_TOO_LARGE: "录音文件过大，请缩短录音时间。",
  VOICE_TOO_LONG: "录音时间过长，请分段录制。",
  VOICE_TOO_SHORT: "录音时间太短，请重新录制。",
  VOICE_TRANSCRIPTION_FAILED: "语音识别失败，请重新录制。",
  VOICE_UNAVAILABLE: "语音识别暂不可用。",
  VOICE_VALIDATION_UNAVAILABLE: "语音服务暂不可用，请稍后再试。",
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

export function userFacingApiError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const message = errorMessages[error.code] ?? fallback;
    return error.requestId ? `${message}（参考号 ${error.requestId}）` : message;
  }
  return fallback;
}
