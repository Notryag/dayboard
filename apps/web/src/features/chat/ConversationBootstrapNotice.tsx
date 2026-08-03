"use client";

import { RotateCw } from "lucide-react";
import { useI18n } from "@/i18n";
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
  const { t } = useI18n();
  return (
    <div className={styles.notice} role="alert">
      <span>{error}</span>
      <button disabled={busy} onClick={onRetry} type="button">
        <RotateCw aria-hidden="true" size={15} />
        {t("chat.reconnect")}
      </button>
    </div>
  );
}
