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
  THREAD_NOT_FOUND: "当前对话已不存在，请重新开始。",
  RUN_NOT_FOUND: "该请求已不存在，请重新提交。",
  COMMAND_ALREADY_IN_PROGRESS: "上一条请求仍在处理中，请稍候。",
  IDEMPOTENCY_CONFLICT: "请求标识已被其他操作使用，请重新提交。",
  CLARIFICATION_CONFLICT: "这个选项已经失效，请重新选择。",
  COMMAND_QUEUE_UNAVAILABLE: "服务暂时繁忙，请稍后重试。",
  RATE_LIMIT_EXCEEDED: "操作过于频繁，请稍后再试。",
  VALIDATION_ERROR: "提交的信息不完整或格式不正确。",
};

export function apiBaseUrl() {
  return process.env.NEXT_PUBLIC_DAYBOARD_API_BASE_URL ?? "http://127.0.0.1:8000";
}

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    credentials: "include",
  });
  if (!response.ok) {
    let body: ApiErrorEnvelope = {};
    try {
      body = (await response.json()) as ApiErrorEnvelope;
    } catch {
      // Non-JSON proxy errors still retain their status and request ID.
    }
    const error = body.error;
    throw new ApiError(
      error?.message ?? `API request failed with ${response.status}`,
      response.status,
      error?.request_id ?? response.headers.get("x-request-id"),
      error?.code ?? `HTTP_${response.status}`,
      error?.details,
    );
  }
  return response;
}

export function userFacingApiError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const message = errorMessages[error.code] ?? fallback;
    return error.requestId ? `${message}（参考号 ${error.requestId}）` : message;
  }
  return fallback;
}
