import { apiFetch } from "@/lib/api/client";
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
      body: JSON.stringify({ identifier, password } satisfies Login),
    })
  ).json()) as Account;
}

export async function requestPasswordReset(email: string): Promise<void> {
  await apiFetch("/api/auth/password-reset/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email } satisfies PasswordReset),
  });
}

export async function confirmPasswordReset(token: string, password: string): Promise<void> {
  await apiFetch("/api/auth/password-reset/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password } satisfies PasswordResetConfirm),
  });
}

export async function logoutAccount(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
}
