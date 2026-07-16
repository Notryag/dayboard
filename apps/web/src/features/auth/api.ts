import { apiFetch } from "@/lib/api/client";

export type Account = {
  user_id: string;
  tenant_id: string;
  username: string;
  email: string | null;
  display_name: string | null;
  timezone: string;
  locale: string;
};

export type Registration = {
  username: string;
  password: string;
  email?: string;
  display_name?: string;
  locale: string;
};

export type AuthCapabilities = {
  password_reset_available: boolean;
};

export async function getAccount(): Promise<Account> {
  return (await (await apiFetch("/api/auth/me")).json()) as Account;
}

export async function getAuthCapabilities(): Promise<AuthCapabilities> {
  return (await (await apiFetch("/api/auth/capabilities")).json()) as AuthCapabilities;
}

export async function registerAccount(body: Registration): Promise<Account> {
  return (await (
    await apiFetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  ).json()) as Account;
}

export async function loginAccount(identifier: string, password: string): Promise<Account> {
  return (await (
    await apiFetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier, password }),
    })
  ).json()) as Account;
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiFetch("/api/auth/password-reset/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export async function confirmPasswordReset(token: string, password: string): Promise<void> {
  await apiFetch("/api/auth/password-reset/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
}

export async function logoutAccount(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
}
