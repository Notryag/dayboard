import { apiClient, requireApiData } from "@/lib/api/typedClient";
import type {
  Account,
  AuthCapabilities,
  Login,
  PasswordReset,
  PasswordResetConfirm,
  Registration,
} from "@/lib/api/types";

export type { Account, AuthCapabilities, Registration } from "@/lib/api/types";

export async function getAccount(): Promise<Account> {
  const { data } = await apiClient.GET("/api/auth/me");
  return requireApiData(data);
}

export async function getAuthCapabilities(): Promise<AuthCapabilities> {
  const { data } = await apiClient.GET("/api/auth/capabilities");
  return requireApiData(data);
}

export async function registerAccount(body: Registration): Promise<Account> {
  const { data } = await apiClient.POST("/api/auth/register", { body });
  return requireApiData(data);
}

export async function loginAccount(identifier: string, password: string): Promise<Account> {
  const body = { identifier, password } satisfies Login;
  const { data } = await apiClient.POST("/api/auth/login", { body });
  return requireApiData(data);
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiClient.POST("/api/auth/password-reset/request", {
    body: { email } satisfies PasswordReset,
  });
}

export async function confirmPasswordReset(token: string, password: string): Promise<void> {
  await apiClient.POST("/api/auth/password-reset/confirm", {
    body: { token, password } satisfies PasswordResetConfirm,
  });
}

export async function logoutAccount(): Promise<void> {
  await apiClient.POST("/api/auth/logout");
}
