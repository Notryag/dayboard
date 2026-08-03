"use client";

import type { RefObject } from "react";
import { Mic, SendHorizontal, Square } from "lucide-react";
import { useI18n } from "@/i18n";
import styles from "./Composer.module.css";

type TextComposerProps = {
  activeRunId: string | null;
  disabled: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  isSubmitting: boolean;
  onCancelRun: () => void;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onSwitchToVoice: () => void;
  value: string;
};

export function TextComposer({
  activeRunId,
  disabled,
  inputRef,
  isSubmitting,
  onCancelRun,
  onChange,
  onSubmit,
  onSwitchToVoice,
  value,
}: TextComposerProps) {
  const { t } = useI18n();
  return (
    <form
      className={`${styles.composer} ${styles.textComposer}`}
      onSubmit={(event) => {
        event.preventDefault();
        if (!isSubmitting) onSubmit(value);
      }}
    >
      <button
        aria-label={t("chat.switchToVoice")}
        className={styles.iconButton}
        disabled={disabled || isSubmitting}
        onClick={onSwitchToVoice}
        title={t("chat.voiceInput")}
        type="button"
      >
        <Mic size={20} strokeWidth={2.2} />
      </button>

      <label className={styles.inputWrap}>
        <span className={styles.srOnly}>{t("chat.inputPlaceholder")}</span>
        <input
          disabled={disabled || isSubmitting}
          onChange={(event) => onChange(event.target.value)}
          placeholder={t("chat.inputPlaceholder")}
          ref={inputRef}
          type="text"
          value={value}
        />
      </label>

      {isSubmitting ? (
        <button
          aria-label={t("chat.stop")}
          className={styles.stopButton}
          disabled={!activeRunId}
          onClick={onCancelRun}
          type="button"
        >
          <Square fill="currentColor" size={17} strokeWidth={2.2} />
        </button>
      ) : (
        <button
          aria-label={t("chat.send")}
          className={styles.sendButton}
          disabled={!value.trim() || disabled}
          type="submit"
        >
          <SendHorizontal size={20} strokeWidth={2.2} />
        </button>
      )}
    </form>
  );
}
