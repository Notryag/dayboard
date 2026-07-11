export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

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
    throw new ApiError(
      `API request failed with ${response.status}`,
      response.status,
      response.headers.get("x-request-id"),
    );
  }
  return response;
}

export function userFacingApiError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.requestId) {
    return `${fallback}（参考号 ${error.requestId}）`;
  }
  return fallback;
}
