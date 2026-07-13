"use client";

import type { RefObject } from "react";
import { Mic, SendHorizontal, Square } from "lucide-react";
import styles from "./Composer.module.css";

type TextComposerProps = {
  activeRunId: string | null;
  disabled: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
  isSubmitting: boolean;
  onCancelRun: () => void;
  onChange: (value: string) => void;
  onSubmit: () => void;
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
  return (
    <form
      className={`${styles.composer} ${styles.textComposer}`}
      onSubmit={(event) => {
        event.preventDefault();
        if (!isSubmitting) onSubmit();
      }}
    >
      <button
        aria-label="切换到语音输入"
        className={styles.iconButton}
        disabled={disabled || isSubmitting}
        onClick={onSwitchToVoice}
        title="语音输入"
        type="button"
      >
        <Mic size={20} strokeWidth={2.2} />
      </button>

      <label className={styles.inputWrap}>
        <span className={styles.srOnly}>输入日程或任务</span>
        <input
          disabled={disabled || isSubmitting}
          onChange={(event) => onChange(event.target.value)}
          placeholder="输入日程或任务"
          ref={inputRef}
          type="text"
          value={value}
        />
      </label>

      {isSubmitting ? (
        <button
          aria-label="停止"
          className={styles.stopButton}
          disabled={!activeRunId}
          onClick={onCancelRun}
          type="button"
        >
          <Square fill="currentColor" size={17} strokeWidth={2.2} />
        </button>
      ) : (
        <button
          aria-label="发送"
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
