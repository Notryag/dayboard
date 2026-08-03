"use client";

import { LoaderCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import styles from "./ScheduleUndoToast.module.css";

type ScheduleUndoToastProps = {
  busy: boolean;
  error: string | null;
  label: string;
  onUndo: () => void;
};

export function ScheduleUndoToast({ busy, error, label, onUndo }: ScheduleUndoToastProps) {
  const { t } = useI18n();
  return (
    <div className={styles.toast} role={error ? "alert" : "status"}>
      <span>{error ?? label}</span>
      {!error ? (
        <button disabled={busy} onClick={onUndo} type="button">
          {busy ? <LoaderCircle aria-hidden="true" className={styles.spinner} size={16} /> : null}
          {t("common.undo")}
        </button>
      ) : null}
    </div>
  );
}
