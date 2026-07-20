"use client";

import { RotateCw } from "lucide-react";
import styles from "./ConversationBootstrapNotice.module.css";

type ConversationBootstrapNoticeProps = {
  busy: boolean;
  error: string;
  onRetry: () => void;
};

export function ConversationBootstrapNotice({
  busy,
  error,
  onRetry,
}: ConversationBootstrapNoticeProps) {
  return (
    <div className={styles.notice} role="alert">
      <span>{error}</span>
      <button disabled={busy} onClick={onRetry} type="button">
        <RotateCw aria-hidden="true" size={15} />
        重新连接
      </button>
    </div>
  );
}
