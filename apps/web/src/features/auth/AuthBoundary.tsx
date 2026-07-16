"use client";

import { FormEvent, useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { AuthProvider, useAuth } from "./AuthProvider";
import { PasswordRecoveryForm } from "./PasswordRecoveryForm";
import styles from "./auth.module.css";

function AuthContent({ children }: { children: React.ReactNode }) {
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
    setError(null);
    setNotice(null);
    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(String(form.get("identifier")), String(form.get("password")));
      } else {
        await register({
          username: String(form.get("username")),
          password: String(form.get("password")),
          email: String(form.get("email") ?? "") || undefined,
          display_name: String(form.get("displayName") ?? "") || undefined,
          locale: navigator.language || "zh-CN",
        });
      }
    } catch (caught) {
      setError(userFacingApiError(caught, mode === "login" ? "登录失败" : "注册失败"));
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return <main className={styles.loading}>正在恢复会话</main>;
  }
  if (account && mode !== "reset") return children;

  const isRecovery = mode === "forgot" || mode === "reset";

  async function resetCompleted() {
    await logout();
    setResetToken(null);
    setMode("login");
    setNotice("密码已更新，请使用新密码登录。");
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
            ? "登录"
            : mode === "register"
              ? "创建账号"
              : mode === "forgot"
                ? "找回密码"
                : "设置新密码"}
        </h1>
        {!isRecovery ? (
          <div className={styles.tabs} aria-label="账号操作">
            <button
              aria-pressed={mode === "login"}
              onClick={() => {
                setError(null);
                setMode("login");
              }}
              type="button"
            >
              登录
            </button>
            <button
              aria-pressed={mode === "register"}
              onClick={() => {
                setError(null);
                setMode("register");
              }}
              type="button"
            >
              注册
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
          <form className={styles.form} onSubmit={submit}>
            {recoveryError ? <p className={styles.error}>{recoveryError}</p> : null}
            {notice ? <p className={styles.notice}>{notice}</p> : null}
            {mode === "login" ? (
              <label>
                <span>用户名或邮箱</span>
                <input autoComplete="username" name="identifier" required />
              </label>
            ) : (
              <>
                <label>
                  <span>用户名</span>
                  <input
                    autoComplete="username"
                    minLength={3}
                    name="username"
                    pattern="[a-zA-Z0-9_.-]+"
                    required
                  />
                </label>
                <label>
                  <span>邮箱（可选）</span>
                  <input autoComplete="email" name="email" type="email" />
                </label>
                <label>
                  <span>显示名称（可选）</span>
                  <input autoComplete="name" name="displayName" />
                </label>
              </>
            )}
            <label>
              <span>密码</span>
              <input
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 10 : 1}
                name="password"
                required
                type="password"
              />
            </label>
            {mode === "login" && passwordResetAvailable ? (
              <button
                className={styles.linkButton}
                onClick={() => setMode("forgot")}
                type="button"
              >
                忘记密码
              </button>
            ) : null}
            {error ? <p className={styles.error}>{error}</p> : null}
            <button className={styles.submit} disabled={isSubmitting} type="submit">
              {isSubmitting ? "正在提交" : mode === "login" ? "登录" : "创建账号"}
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
