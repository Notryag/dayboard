"use client";

import { FormEvent, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { confirmPasswordReset, requestPasswordReset } from "./api";
import styles from "./auth.module.css";

type PasswordRecoveryFormProps = {
  resetToken: string | null;
  onBack: () => void;
  onResetCompleted: () => Promise<void>;
};

export function PasswordRecoveryForm({
  resetToken,
  onBack,
  onResetCompleted,
}: PasswordRecoveryFormProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRequested, setIsRequested] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setIsSubmitting(true);
    try {
      await requestPasswordReset(String(form.get("email")));
      setIsRequested(true);
    } catch (caught) {
      setError(userFacingApiError(caught, "暂时无法发送重置邮件"));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    const confirmation = String(form.get("passwordConfirmation"));
    setError(null);
    if (password !== confirmation) {
      setError("两次输入的密码不一致");
      return;
    }
    if (!resetToken) {
      setError("重置链接无效，请重新申请");
      return;
    }
    setIsSubmitting(true);
    try {
      await confirmPasswordReset(resetToken, password);
      await onResetCompleted();
    } catch (caught) {
      setError(userFacingApiError(caught, "重置链接无效或已过期"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <button className={styles.backButton} onClick={onBack} type="button">
        <ArrowLeft aria-hidden="true" size={18} />
        返回登录
      </button>
      {resetToken ? (
        <form className={styles.form} onSubmit={submitPassword}>
          <label>
            <span>新密码</span>
            <input autoComplete="new-password" minLength={10} name="password" required type="password" />
          </label>
          <label>
            <span>确认新密码</span>
            <input
              autoComplete="new-password"
              minLength={10}
              name="passwordConfirmation"
              required
              type="password"
            />
          </label>
          {error ? <p className={styles.error}>{error}</p> : null}
          <button className={styles.submit} disabled={isSubmitting} type="submit">
            {isSubmitting ? "正在重置" : "设置新密码"}
          </button>
        </form>
      ) : isRequested ? (
        <p className={styles.notice}>如果该邮箱已绑定账号，重置邮件将很快送达。</p>
      ) : (
        <form className={styles.form} onSubmit={submitRequest}>
          <label>
            <span>绑定邮箱</span>
            <input autoComplete="email" name="email" required type="email" />
          </label>
          {error ? <p className={styles.error}>{error}</p> : null}
          <button className={styles.submit} disabled={isSubmitting} type="submit">
            {isSubmitting ? "正在发送" : "发送重置邮件"}
          </button>
        </form>
      )}
    </>
  );
}
