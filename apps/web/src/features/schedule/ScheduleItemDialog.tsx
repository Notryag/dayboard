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
import { Button } from "@/components/ui/button";
import {
  DialogClose,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { userFacingApiError } from "@/lib/api/client";
import { cancelCalendarEntry, cancelTaskItem } from "./api";
import { completeScheduleItem } from "./scheduleItemActions";
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

type ScheduleItemDialogProps = {
  initialError: string | null;
  item: ScheduleDisplayItem;
  timezone: string;
  onBusyChange: (busy: boolean) => void;
  onChanged: (change?: ScheduleChange) => void;
  onClose: () => void;
};

export function ScheduleItemDialog({
  initialError,
  item,
  timezone,
  onBusyChange,
  onChanged,
  onClose,
}: ScheduleItemDialogProps) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [error, setError] = useState<string | null>(initialError);
  const Icon = iconForScheduleItem(item.kind);
  const reminder = formatScheduleReminder(item.value.reminder);
  const status = scheduleItemStatus(item);

  async function complete() {
    setBusy(true);
    onBusyChange(true);
    setError(null);
    try {
      onChanged(await completeScheduleItem(item));
      onClose();
    } catch (caught) {
      setError(userFacingApiError(caught, "完成失败，请刷新后重试。"));
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
      setError(userFacingApiError(caught, "取消失败，请刷新后重试。"));
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }

  return (
    <DialogContent
      aria-label="安排详情"
      aria-describedby={undefined}
      className={styles.dialog}
      overlayClassName={styles.dialogLayer}
      showCloseButton={false}
    >
        <header className={styles.dialogHeader}>
          <span
            aria-hidden="true"
            className={`${styles.dialogIcon} ${item.kind === "task" ? styles.taskIcon : ""}`}
          >
            {createElement(Icon, { size: 21 })}
          </span>
          <div className={styles.dialogHeading}>
            <span>{editing ? "编辑" : item.kind === "calendar" ? "日程" : "待办"}</span>
            <DialogTitle>{scheduleItemTitle(item)}</DialogTitle>
          </div>
          <DialogClose
            disabled={busy}
            render={
              <Button
                aria-label="关闭详情"
                className={styles.closeButton}
                size="icon"
                title="关闭"
                type="button"
                variant="ghost"
              />
            }
          >
              <X size={19} />
          </DialogClose>
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
              <span>{scheduleItemMeta(item, timezone, "detail")}</span>
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
            {status !== "open" ? <p className={styles.status}>{status === "completed" ? "已完成" : "已取消"}</p> : null}
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
            <p>确定取消“{scheduleItemTitle(item)}”？</p>
            <div>
              <button disabled={busy} onClick={() => setConfirmCancel(false)} type="button">返回</button>
              <button className={styles.dangerButton} disabled={busy} onClick={() => void cancel()} type="button">
                {busy ? <LoaderCircle className={styles.spinner} size={16} /> : <Trash2 size={16} />}
                确认取消
              </button>
            </div>
          </div>
        ) : null}

        {!editing && !confirmCancel && status === "open" ? (
          <footer className={styles.actions}>
            <button className={styles.editButton} disabled={busy} onClick={() => setEditing(true)} type="button">
              <Pencil aria-hidden="true" size={16} />修改
            </button>
            <button className={styles.completeButton} disabled={busy} onClick={() => void complete()} type="button">
              {busy ? <LoaderCircle className={styles.spinner} size={16} /> : <Check size={16} />}标记完成
            </button>
            <button className={styles.cancelButton} disabled={busy} onClick={() => setConfirmCancel(true)} type="button">
              <Trash2 aria-hidden="true" size={16} />取消
            </button>
          </footer>
        ) : null}
    </DialogContent>
  );
}
