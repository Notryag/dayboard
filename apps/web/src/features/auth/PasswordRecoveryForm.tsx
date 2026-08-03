"use client";

import { FormEvent, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useI18n } from "@/i18n";
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
  const { t, locale } = useI18n();
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
      setError(userFacingApiError(caught, t("auth.resetEmailUnavailable"), locale));
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
      setError(t("auth.passwordMismatchShort"));
      return;
    }
    if (!resetToken) {
      setError(t("auth.invalidResetLink"));
      return;
    }
    setIsSubmitting(true);
    try {
      await confirmPasswordReset(resetToken, password);
      await onResetCompleted();
    } catch (caught) {
      setError(userFacingApiError(caught, t("auth.invalidOrExpiredResetLink"), locale));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <button className={styles.backButton} onClick={onBack} type="button">
        <ArrowLeft aria-hidden="true" size={18} />
        {t("auth.backToLogin")}
      </button>
      {resetToken ? (
        <form className={styles.form} onSubmit={submitPassword}>
          <label>
            <span>{t("auth.newPassword")}</span>
            <input autoComplete="new-password" minLength={10} name="password" required type="password" />
          </label>
          <label>
            <span>{t("auth.confirmNewPassword")}</span>
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
            {isSubmitting ? t("auth.resetting") : t("auth.setNewPassword")}
          </button>
        </form>
      ) : isRequested ? (
        <p className={styles.notice}>{t("auth.resetNotice")}</p>
      ) : (
        <form className={styles.form} onSubmit={submitRequest}>
          <label>
            <span>{t("auth.boundEmail")}</span>
            <input autoComplete="email" name="email" required type="email" />
          </label>
          {error ? <p className={styles.error}>{error}</p> : null}
          <button className={styles.submit} disabled={isSubmitting} type="submit">
            {isSubmitting ? t("auth.sending") : t("auth.sendResetEmail")}
          </button>
        </form>
      )}
    </>
  );
}
