"use client";

import { createElement, useEffect, useRef, useState } from "react";
import { Check, LoaderCircle } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { userFacingApiError } from "@/lib/api/client";
import { completeScheduleItem } from "./scheduleItemActions";
import {
  iconForScheduleItem,
  scheduleItemMeta,
  scheduleItemStatus,
  scheduleItemTitle,
} from "./scheduleItemPresentation";
import { ScheduleItemDialog } from "./ScheduleItemDialog";
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
  const itemRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [directError, setDirectError] = useState<string | null>(null);
  const Icon = iconForScheduleItem(item.kind);
  const status = scheduleItemStatus(item);
  const showCompletionControl = variant !== "chat" && status !== "cancelled";

  useEffect(() => {
    if (highlighted) itemRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlighted]);

  async function completeFromCard() {
    if (status !== "open" || completing) return;
    setCompleting(true);
    setDirectError(null);
    try {
      onChanged(await completeScheduleItem(item));
    } catch (caught) {
      setDirectError(userFacingApiError(caught, "完成失败，请刷新后重试。"));
      setOpen(true);
    } finally {
      setCompleting(false);
    }
  }

  return (
    <Dialog
      disablePointerDismissal={dialogBusy}
      open={open}
      onOpenChange={(nextOpen) => {
        if (!dialogBusy) setOpen(nextOpen);
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
          aria-label={`查看${item.kind === "calendar" ? "日程" : "待办"}：${scheduleItemTitle(item)}`}
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
            <span>{scheduleItemMeta(item, timezone, variant)}</span>
          </span>
        </button>
        {showCompletionControl ? (
          <button
            aria-label={`${status === "completed" ? "已完成" : "完成"}${item.kind === "calendar" ? "日程" : "待办"}：${scheduleItemTitle(item)}`}
            aria-pressed={status === "completed"}
            className={styles.completionControl}
            disabled={status === "completed" || completing}
            onClick={() => void completeFromCard()}
            title={status === "completed" ? "已完成" : "标记完成"}
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
        <ScheduleItemDialog
          initialError={directError}
          item={item}
          onBusyChange={setDialogBusy}
          onChanged={onChanged}
          onClose={() => setOpen(false)}
          timezone={timezone}
        />
      ) : null}
    </Dialog>
  );
}
