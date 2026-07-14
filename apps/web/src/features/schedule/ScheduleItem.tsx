"use client";

import { createElement, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  Bell,
  CalendarClock,
  Check,
  ChevronRight,
  Coffee,
  Dumbbell,
  GraduationCap,
  House,
  ListTodo,
  LoaderCircle,
  MapPin,
  Package,
  Pencil,
  Plane,
  ShoppingBag,
  Stethoscope,
  Trash2,
  TrainFront,
  Utensils,
  Users,
  Waves,
  X,
} from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import {
  cancelCalendarEntry,
  cancelTaskItem,
  completeTaskItem,
} from "./api";
import { formatScheduleTime } from "./date";
import type {
  CalendarEntry,
  ScheduleDisplayItem,
} from "./types";
import styles from "./ScheduleItem.module.css";

type ScheduleItemProps = {
  item: ScheduleDisplayItem;
  timezone: string;
  variant?: "agenda" | "chat" | "task";
  onChanged: () => void;
  onEdit: (item: ScheduleDisplayItem) => void;
};

type IconComponent = typeof CalendarClock;

function iconForTitle(title: string, kind: ScheduleDisplayItem["kind"]): IconComponent {
  const normalized = title.toLowerCase();
  const matches = (...keywords: string[]) => keywords.some((keyword) => normalized.includes(keyword));
  if (matches("游泳", "泳池", "swim")) return Waves;
  if (matches("吃饭", "午餐", "晚餐", "早餐", "餐厅", "饭")) return Utensils;
  if (matches("咖啡", "coffee")) return Coffee;
  if (matches("会议", "开会", "评审", "面试", "meeting")) return Users;
  if (matches("购物", "买", "超市", "商场", "shopping")) return ShoppingBag;
  if (matches("健身", "运动", "跑步", "瑜伽", "gym", "run")) return Dumbbell;
  if (matches("学习", "课程", "补习", "上课", "study", "class")) return GraduationCap;
  if (matches("医院", "看病", "医生", "体检", "doctor")) return Stethoscope;
  if (matches("飞机", "航班", "机场", "flight")) return Plane;
  if (matches("火车", "高铁", "地铁", "train")) return TrainFront;
  if (matches("开车", "驾车", "驾驶", "car")) return MapPin;
  if (matches("回家", "家里", "home")) return House;
  if (matches("快递", "包裹", "取件", "package")) return Package;
  if (kind === "task") return ListTodo;
  return CalendarClock;
}

function formatReminder(reminder: CalendarEntry["reminder"]) {
  if (!reminder) return null;
  if (reminder.offset === "PT0M") return "按时提醒";
  return `提前 ${reminder.offset.replace(/^PT|^P/, "").replace("H", "小时").replace("M", "分钟").replace("D", "天")}`;
}

function itemTitle(item: ScheduleDisplayItem) {
  return item.value.title;
}

function formatScheduleDateTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone,
  }).format(new Date(value));
}

function itemMeta(
  item: ScheduleDisplayItem,
  timezone: string,
  variant: "agenda" | "chat" | "task" | "detail",
) {
  if (item.kind === "calendar") {
    if (item.value.status === "cancelled") return "日程 · 已取消";
    if (variant === "agenda") {
      return item.value.end_time
        ? `日程 · 至 ${formatScheduleTime(item.value.end_time, timezone)}`
        : "日程";
    }
    const start = formatScheduleDateTime(item.value.start_time, timezone);
    const end = item.value.end_time ? ` - ${formatScheduleTime(item.value.end_time, timezone)}` : "";
    return `日程 · ${start}${end}`;
  }
  if (item.value.status === "completed") return "待办 · 已完成";
  if (item.value.status === "cancelled") return "待办 · 已取消";
  if (variant === "agenda" || variant === "task") return "待办";
  return item.value.due_at
    ? `待办 · ${formatScheduleDateTime(item.value.due_at, timezone)}`
    : "待办清单";
}

function itemStatus(item: ScheduleDisplayItem) {
  if (item.kind === "calendar") return item.value.status === "cancelled" ? "cancelled" : "open";
  return item.value.status;
}

export function ScheduleItem({
  item,
  timezone,
  variant = "agenda",
  onChanged,
  onEdit,
}: ScheduleItemProps) {
  const [open, setOpen] = useState(false);
  const Icon = iconForTitle(itemTitle(item), item.kind);

  return (
    <>
      <button
        aria-label={`查看${item.kind === "calendar" ? "日程" : "待办"}：${itemTitle(item)}`}
        className={`${styles.item} ${styles[variant]} ${
          itemStatus(item) !== "open" ? styles[itemStatus(item)] : ""
        }`}
        onClick={() => setOpen(true)}
        type="button"
      >
        <span aria-hidden="true" className={`${styles.icon} ${styles[item.kind]}`}>
          {createElement(Icon, { size: variant === "chat" ? 17 : 18, strokeWidth: 2.1 })}
        </span>
        <span className={styles.copy}>
          <strong>{itemTitle(item)}</strong>
          <span>{itemMeta(item, timezone, variant)}</span>
        </span>
        {variant !== "task" ? <ChevronRight aria-hidden="true" size={17} /> : null}
      </button>
      {open
        ? createPortal(
            <ScheduleItemDialog
              item={item}
              onChanged={onChanged}
              onClose={() => setOpen(false)}
              onEdit={() => {
                setOpen(false);
                onEdit(item);
              }}
              timezone={timezone}
            />,
            document.body,
          )
        : null}
    </>
  );
}

type ScheduleItemDialogProps = {
  item: ScheduleDisplayItem;
  timezone: string;
  onChanged: () => void;
  onClose: () => void;
  onEdit: () => void;
};

function ScheduleItemDialog({
  item,
  timezone,
  onChanged,
  onClose,
  onEdit,
}: ScheduleItemDialogProps) {
  const [busy, setBusy] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const Icon = iconForTitle(itemTitle(item), item.kind);
  const reminder = formatReminder(item.value.reminder);
  const status = itemStatus(item);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [busy, onClose]);

  async function complete() {
    if (item.kind !== "task") return;
    setBusy(true);
    setError(null);
    try {
      await completeTaskItem(item.value);
      onChanged();
      onClose();
    } catch (caught) {
      setError(userFacingApiError(caught, "完成待办失败，请刷新后重试。"));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
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
    }
  }

  return (
    <div
      className={styles.dialogLayer}
      onPointerDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
      role="presentation"
    >
      <section
        aria-label="安排详情"
        aria-modal="true"
        className={styles.dialog}
        onPointerDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className={styles.dialogHeader}>
          <span aria-hidden="true" className={`${styles.dialogIcon} ${styles[item.kind]}`}>
            {createElement(Icon, { size: 21 })}
          </span>
          <div className={styles.dialogHeading}>
            <span>{item.kind === "calendar" ? "日程" : "待办"}</span>
            <h2>{itemTitle(item)}</h2>
          </div>
          <button aria-label="关闭详情" className={styles.closeButton} disabled={busy} onClick={onClose} title="关闭" type="button">
            <X size={19} />
          </button>
        </header>

        <div className={styles.details}>
          <p className={styles.detailLine}>
            {item.kind === "calendar" ? (
              <CalendarClock aria-hidden="true" size={17} />
            ) : (
              <ListTodo aria-hidden="true" size={17} />
            )}
            <span>{itemMeta(item, timezone, "detail")}</span>
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

        {confirmCancel ? (
          <div className={styles.confirmation}>
            <p>确定取消“{itemTitle(item)}”？</p>
            <div>
              <button disabled={busy} onClick={() => setConfirmCancel(false)} type="button">
                返回
              </button>
              <button className={styles.dangerButton} disabled={busy} onClick={() => void cancel()} type="button">
                {busy ? <LoaderCircle className={styles.spinner} size={16} /> : <Trash2 size={16} />}
                确认取消
              </button>
            </div>
          </div>
        ) : null}

        {!confirmCancel && status === "open" ? (
          <footer className={styles.actions}>
            <button className={styles.editButton} disabled={busy} onClick={onEdit} type="button">
              <Pencil aria-hidden="true" size={16} />
              修改
            </button>
            {item.kind === "task" ? (
              <button className={styles.completeButton} disabled={busy} onClick={() => void complete()} type="button">
                {busy ? <LoaderCircle className={styles.spinner} size={16} /> : <Check size={16} />}
                完成
              </button>
            ) : null}
            <button className={styles.cancelButton} disabled={busy} onClick={() => setConfirmCancel(true)} type="button">
              <Trash2 aria-hidden="true" size={16} />
              取消
            </button>
          </footer>
        ) : null}
      </section>
    </div>
  );
}
