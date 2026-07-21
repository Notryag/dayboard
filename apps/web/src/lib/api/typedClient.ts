import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { apiBaseUrl, apiErrorFromResponse } from "./client";

const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (!response.ok) throw await apiErrorFromResponse(response);
    return response;
  },
};

export const apiClient = createClient<paths>({
  baseUrl: apiBaseUrl(),
  credentials: "include",
});

apiClient.use(errorMiddleware);

export function requireApiData<T>(data: T | undefined): T {
  if (data === undefined) throw new Error("API returned no response body");
  return data;
}
