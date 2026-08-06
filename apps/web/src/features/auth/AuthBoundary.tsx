"use client";

import { FormEvent, useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { useI18n } from "@/i18n";
import { userFacingApiError } from "@/lib/api/client";
import { AuthProvider, useAuth } from "./AuthProvider";
import { PasswordInput } from "./PasswordInput";
import { PasswordRecoveryForm } from "./PasswordRecoveryForm";
import styles from "./auth.module.css";

function AuthContent({ children }: { children: React.ReactNode }) {
  const { t, locale } = useI18n();
  const {
    account,
    isLoading,
    login,
    logout,
    passwordResetAvailable,
    recoveryError,
    register,
  } = useAuth();
  const [mode, setMode] = useState<"login" | "register" | "forgot" | "reset">("login");
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("reset_token");
    if (!token) return;
    url.searchParams.delete("reset_token");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    const timer = window.setTimeout(() => {
      setResetToken(token);
      setMode("reset");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (mode === "register" && password !== String(form.get("confirmPassword"))) {
      setError(t("auth.passwordMismatch"));
      return;
    }
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(String(form.get("identifier")), password);
      } else {
        await register({
          username: String(form.get("username")),
          password,
          email: String(form.get("email") ?? "") || undefined,
          display_name: String(form.get("displayName") ?? "") || undefined,
          locale,
        });
      }
    } catch (caught) {
      setError(userFacingApiError(
        caught,
        mode === "login" ? t("auth.loginFailed") : t("auth.registerFailed"),
        locale,
      ));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return <main className={styles.loading}>{t("auth.loadingSession")}</main>;
  }
  if (account && mode !== "reset") return children;

  const isRecovery = mode === "forgot" || mode === "reset";

  async function resetCompleted() {
    await logout();
    setResetToken(null);
    setMode("login");
    setNotice(t("auth.passwordUpdated"));
  }

  function returnToLogin() {
    setResetToken(null);
    setError(null);
    setMode("login");
  }

  return (
    <main className={styles.page}>
      <section className={styles.authPanel} aria-labelledby="auth-title">
        <div className={styles.brand}>
          <CalendarDays aria-hidden="true" size={24} />
          <span>Dayboard</span>
        </div>
        <h1 id="auth-title">
          {mode === "login"
            ? t("auth.login")
            : mode === "register"
              ? t("auth.createAccount")
              : mode === "forgot"
                ? t("auth.recoverPassword")
                : t("auth.setNewPassword")}
        </h1>
        {!isRecovery ? (
          <div className={styles.tabs} aria-label={t("auth.login")}>
            <button
              aria-pressed={mode === "login"}
              onClick={() => {
                setError(null);
                setMode("login");
              }}
              type="button"
            >
              {t("auth.login")}
            </button>
            <button
              aria-pressed={mode === "register"}
              onClick={() => {
                setError(null);
                setMode("register");
              }}
              type="button"
            >
              {t("auth.register")}
            </button>
          </div>
        ) : null}
        {isRecovery ? (
          <PasswordRecoveryForm
            onBack={returnToLogin}
            onResetCompleted={resetCompleted}
            resetToken={resetToken}
          />
        ) : (
          <form className={styles.form} key={mode} onSubmit={submit}>
            {recoveryError ? <p className={styles.error}>{recoveryError}</p> : null}
            {notice ? <p className={styles.notice}>{notice}</p> : null}
            {mode === "login" ? (
              <label>
                <span>{t("auth.usernameOrEmail")}</span>
                <input autoComplete="username" name="identifier" required />
              </label>
            ) : (
              <>
                <label>
                  <span>{t("auth.username")}</span>
                  <input
                    autoComplete="username"
                    minLength={3}
                    name="username"
                    pattern="[a-zA-Z0-9_.\-]+"
                    required
                  />
                </label>
                <label>
                  <span>{t("auth.emailOptional")}</span>
                  <input autoComplete="email" name="email" type="email" />
                </label>
                <label>
                  <span>{t("auth.displayNameOptional")}</span>
                  <input autoComplete="name" name="displayName" />
                </label>
              </>
            )}
            <PasswordInput
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              label={t("auth.password")}
              minLength={mode === "register" ? 10 : 1}
              name="password"
            />
            {mode === "register" ? (
              <PasswordInput
                autoComplete="new-password"
                label={t("auth.confirmPassword")}
                minLength={10}
                name="confirmPassword"
              />
            ) : null}
            {mode === "login" && passwordResetAvailable ? (
              <button
                className={styles.linkButton}
                onClick={() => setMode("forgot")}
                type="button"
              >
                {t("auth.forgotPassword")}
              </button>
            ) : null}
            {error ? <p className={styles.error}>{error}</p> : null}
            <button className={styles.submit} disabled={isSubmitting} type="submit">
              {isSubmitting ? t("auth.submit") : mode === "login" ? t("auth.login") : t("auth.createAccount")}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}

export function AuthBoundary({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthContent>{children}</AuthContent>
    </AuthProvider>
  );
}
