"use client";

import { createElement, useState } from "react";
import {
  AlertCircle,
  Bell,
  CalendarClock,
  Check,
  ListTodo,
  LoaderCircle,
  Pencil,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import {
  SheetClose,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet";
import { userFacingApiError } from "@/lib/api/client";
import { cancelCalendarEntry, cancelTaskItem } from "./api";
import { completeScheduleItem, reopenScheduleItem } from "./scheduleItemActions";
import {
  formatScheduleReminder,
  iconForScheduleItem,
  scheduleItemMeta,
  scheduleItemStatus,
  scheduleItemTitle,
} from "./scheduleItemPresentation";
import { ScheduleItemEditForm } from "./ScheduleItemEditForm";
import type { ScheduleChange, ScheduleDisplayItem } from "./types";
import styles from "./ScheduleItem.module.css";

type ScheduleItemSheetProps = {
  initialError: string | null;
  item: ScheduleDisplayItem;
  timezone: string;
  onBusyChange: (busy: boolean) => void;
  onChanged: (change?: ScheduleChange) => void;
  onClose: () => void;
};

export function ScheduleItemSheet({
  initialError,
  item,
  timezone,
  onBusyChange,
  onChanged,
  onClose,
}: ScheduleItemSheetProps) {
  const { locale, t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const Icon = iconForScheduleItem(item.kind);
  const reminder = formatScheduleReminder(item.value.reminder, locale);
  const status = scheduleItemStatus(item);

  async function toggleCompletion() {
    setBusy(true);
    onBusyChange(true);
    setError(null);
    try {
      onChanged(await (status === "completed" ? reopenScheduleItem(item, locale) : completeScheduleItem(item, locale)));
      onClose();
    } catch (caught) {
      setError(userFacingApiError(caught, t("schedule.statusUpdateFailed"), locale));
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }

  async function cancel() {
    setBusy(true);
    onBusyChange(true);
    setError(null);
    try {
      if (item.kind === "calendar") await cancelCalendarEntry(item.value);
      else await cancelTaskItem(item.value);
      onChanged();
      onClose();
    } catch (caught) {
      setError(userFacingApiError(caught, t("schedule.cancelFailed"), locale));
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }

  return (
    <SheetContent
      aria-label={t("schedule.details")}
      aria-describedby={undefined}
      className={styles.sheet}
      overlayClassName={styles.sheetLayer}
      side="bottom"
      showCloseButton={false}
    >
        <header className={styles.sheetHeader}>
          <span
            aria-hidden="true"
            className={`${styles.sheetIcon} ${item.kind === "task" ? styles.taskIcon : ""}`}
          >
            {createElement(Icon, { size: 21 })}
          </span>
          <div className={styles.sheetHeading}>
            <span>{editing ? t("schedule.edit") : item.kind === "calendar" ? t("schedule.calendar") : t("schedule.task")}</span>
            <SheetTitle>{scheduleItemTitle(item)}</SheetTitle>
          </div>
          <SheetClose
            disabled={busy}
            render={
              <Button
                aria-label={t("schedule.closeDetails")}
                className={styles.closeButton}
                size="icon"
                title={t("common.close")}
                type="button"
                variant="ghost"
              />
            }
          >
              <X size={19} />
          </SheetClose>
        </header>

        {editing ? (
          <ScheduleItemEditForm
            item={item}
            onCancel={() => setEditing(false)}
            onSaved={(change) => { onChanged(change); onClose(); }}
            timezone={timezone}
          />
        ) : (
          <div className={styles.details}>
            <p className={styles.detailLine}>
              {item.kind === "calendar" ? <CalendarClock aria-hidden="true" size={17} /> : <ListTodo aria-hidden="true" size={17} />}
              <span>{scheduleItemMeta(item, timezone, "detail", locale)}</span>
            </p>
            {item.kind === "calendar" && item.value.participants.length ? (
              <p className={styles.detailLine}>
                <Users aria-hidden="true" size={17} />
                <span>{item.value.participants.join("、")}</span>
              </p>
            ) : null}
            {reminder ? (
              <p className={styles.detailLine}>
                <Bell aria-hidden="true" size={17} />
                <span>{reminder}</span>
              </p>
            ) : null}
            {status !== "open" ? <p className={styles.status}>{status === "completed" ? t("schedule.completed") : t("schedule.cancelled")}</p> : null}
            {error ? (
              <p className={styles.error} role="alert">
                <AlertCircle aria-hidden="true" size={16} />
                <span>{error}</span>
              </p>
            ) : null}
          </div>
        )}

        {!editing && confirmCancel ? (
          <div className={styles.confirmation}>
            <p>{t("schedule.cancelQuestion", { title: scheduleItemTitle(item) })}</p>
            <div>
              <button disabled={busy} onClick={() => setConfirmCancel(false)} type="button">{t("schedule.return")}</button>
              <button className={styles.dangerButton} disabled={busy} onClick={() => void cancel()} type="button">
                {busy ? <LoaderCircle className={styles.spinner} size={16} /> : <Trash2 size={16} />}
                {t("schedule.confirmCancel")}
              </button>
            </div>
          </div>
        ) : null}

        {!editing && !confirmCancel && (status === "open" || status === "completed") ? (
          <footer className={styles.actions}>
            {status === "open" ? (
              <button className={styles.editButton} disabled={busy} onClick={() => setEditing(true)} type="button">
                <Pencil aria-hidden="true" size={16} />{t("schedule.modify")}
              </button>
            ) : null}
            <button className={styles.completeButton} disabled={busy} onClick={() => void toggleCompletion()} type="button">
              {busy ? <LoaderCircle className={styles.spinner} size={16} /> : <Check size={16} />}
              {status === "completed" ? t("schedule.markIncomplete") : t("schedule.markComplete")}
            </button>
            {status === "open" ? (
              <button className={styles.cancelButton} disabled={busy} onClick={() => setConfirmCancel(true)} type="button">
                <Trash2 aria-hidden="true" size={16} />{t("common.cancel")}
              </button>
            ) : null}
          </footer>
        ) : null}
    </SheetContent>
  );
}
