import {
  CalendarClock,
  ListTodo,
  type LucideIcon,
} from "lucide-react";
import { formatScheduleTime } from "./date";
import type { CalendarEntry, ScheduleDisplayItem } from "./types";

export function iconForScheduleItem(kind: ScheduleDisplayItem["kind"]): LucideIcon {
  return kind === "task" ? ListTodo : CalendarClock;
}

export function formatScheduleReminder(reminder: CalendarEntry["reminder"]) {
  if (!reminder) return null;
  if (reminder.offset === "PT0M") return "按时提醒";
  return `提前 ${reminder.offset.replace(/^PT|^P/, "").replace("H", "小时").replace("M", "分钟").replace("D", "天")}`;
}

export function scheduleItemTitle(item: ScheduleDisplayItem) {
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

function formatDuration(startTime: string, endTime: string | null) {
  if (!endTime) return "未设置时长";
  const minutes = Math.round((Date.parse(endTime) - Date.parse(startTime)) / 60000);
  if (minutes <= 0) return "未设置时长";
  if (minutes < 60) return `持续 ${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `持续 ${hours} 小时 ${remainder} 分钟` : `持续 ${hours} 小时`;
}

export function scheduleItemMeta(
  item: ScheduleDisplayItem,
  timezone: string,
  variant: "agenda" | "chat" | "task" | "detail",
) {
  if (item.kind === "calendar") {
    if (item.value.status === "cancelled") return "日程 · 已取消";
    if (variant === "agenda") {
      return formatDuration(item.value.start_time, item.value.end_time);
    }
    const start = formatScheduleDateTime(item.value.start_time, timezone);
    const end = item.value.end_time ? ` - ${formatScheduleTime(item.value.end_time, timezone)}` : "";
    return `${start}${end}`;
  }
  if (item.value.status === "completed") return "待办 · 已完成";
  if (item.value.status === "cancelled") return "待办 · 已取消";
  if (variant === "agenda") return "到期待办";
  if (variant === "task") return item.value.due_at ? "待办" : "未安排时间";
  return item.value.due_at
    ? `待办 · ${formatScheduleDateTime(item.value.due_at, timezone)}`
    : "待办清单";
}

export function scheduleItemStatus(item: ScheduleDisplayItem) {
  if (item.kind === "calendar") {
    if (item.value.status === "cancelled") return "cancelled";
    if (item.value.status === "completed") return "completed";
    return "open";
  }
  return item.value.status;
}
