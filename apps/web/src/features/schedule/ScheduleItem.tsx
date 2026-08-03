"use client";

import { createElement, useEffect, useRef, useState } from "react";
import { Check, LoaderCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import { Sheet } from "@/components/ui/sheet";
import { userFacingApiError } from "@/lib/api/client";
import { completeScheduleItem, reopenScheduleItem } from "./scheduleItemActions";
import {
  iconForScheduleItem,
  scheduleItemMeta,
  scheduleItemStatus,
  scheduleItemTitle,
} from "./scheduleItemPresentation";
import { ScheduleItemSheet } from "./ScheduleItemSheet";
import type { ScheduleChange, ScheduleDisplayItem } from "./types";
import styles from "./ScheduleItem.module.css";

type ScheduleItemProps = {
  highlighted?: boolean;
  item: ScheduleDisplayItem;
  timezone: string;
  variant?: "agenda" | "chat" | "task";
  onChanged: (change?: ScheduleChange) => void;
};

export function ScheduleItem({
  highlighted = false,
  item,
  timezone,
  variant = "agenda",
  onChanged,
}: ScheduleItemProps) {
  const { locale, t } = useI18n();
  const itemRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [sheetBusy, setSheetBusy] = useState(false);
  const [directError, setDirectError] = useState<string | null>(null);
  const Icon = iconForScheduleItem(item.kind);
  const status = scheduleItemStatus(item);
  const showCompletionControl = variant !== "chat" && status !== "cancelled";

  useEffect(() => {
    if (highlighted) itemRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlighted]);

  async function toggleCompletionFromCard() {
    if ((status !== "open" && status !== "completed") || completing) return;
    setCompleting(true);
    setDirectError(null);
    try {
      onChanged(await (status === "completed" ? reopenScheduleItem(item, locale) : completeScheduleItem(item, locale)));
    } catch (caught) {
      setDirectError(userFacingApiError(caught, t("schedule.statusUpdateFailed"), locale));
      setOpen(true);
    } finally {
      setCompleting(false);
    }
  }

  return (
    <Sheet
      disablePointerDismissal={sheetBusy}
      open={open}
      onOpenChange={(nextOpen) => {
        if (!sheetBusy) setOpen(nextOpen);
      }}
    >
      <div
        className={`${styles.item} ${styles[variant]} ${
          status !== "open" ? styles[status] : ""
        } ${item.kind === "calendar" ? styles.kindCalendar : styles.kindTask} ${
          !showCompletionControl ? styles.withoutCompletion : ""
        } ${highlighted ? styles.highlighted : ""
        }`}
        ref={itemRef}
        data-reminder-highlighted={highlighted ? "true" : undefined}
      >
        <button
          aria-label={`${t("common.more")} ${item.kind === "calendar" ? t("schedule.calendar") : t("schedule.task")}: ${scheduleItemTitle(item)}`}
          className={styles.itemMain}
          onClick={() => {
            setDirectError(null);
            setOpen(true);
          }}
          type="button"
        >
          <span
            aria-hidden="true"
            className={`${styles.icon} ${item.kind === "task" ? styles.taskIcon : ""}`}
          >
            {createElement(Icon, { size: variant === "chat" ? 17 : 18, strokeWidth: 2.1 })}
          </span>
          <span className={styles.copy}>
            <strong>{scheduleItemTitle(item)}</strong>
            <span className={styles.metaRow}>
              <span className={styles.metaText}>{scheduleItemMeta(item, timezone, variant, locale)}</span>
              {status === "completed" ? <span className={styles.completedBadge}>{t("schedule.completed")}</span> : null}
            </span>
          </span>
        </button>
        {showCompletionControl ? (
          <button
            aria-label={`${status === "completed" ? t("schedule.markIncomplete") : t("schedule.markComplete")} ${item.kind === "calendar" ? t("schedule.calendar") : t("schedule.task")}: ${scheduleItemTitle(item)}`}
            aria-pressed={status === "completed"}
            className={styles.completionControl}
            disabled={completing}
            onClick={() => void toggleCompletionFromCard()}
            title={status === "completed" ? t("schedule.markIncomplete") : t("schedule.markComplete")}
            type="button"
          >
            {completing ? (
              <LoaderCircle className={styles.spinner} size={15} />
            ) : status === "completed" ? (
              <Check aria-hidden="true" size={16} strokeWidth={2.8} />
            ) : null}
          </button>
        ) : null}
      </div>
      {open ? (
        <ScheduleItemSheet
          initialError={directError}
          item={item}
          onBusyChange={setSheetBusy}
          onChanged={onChanged}
          onClose={() => setOpen(false)}
          timezone={timezone}
        />
      ) : null}
    </Sheet>
  );
}
