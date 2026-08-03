import {
  CalendarClock,
  ListTodo,
  type LucideIcon,
} from "lucide-react";
import { getMessage, type Locale } from "@/i18n";
import { formatScheduleTime } from "./date";
import type { CalendarEntry, ScheduleDisplayItem } from "./types";

export function iconForScheduleItem(kind: ScheduleDisplayItem["kind"]): LucideIcon {
  return kind === "task" ? ListTodo : CalendarClock;
}

export function formatScheduleReminder(reminder: CalendarEntry["reminder"], locale: Locale = "zh-CN") {
  if (!reminder) return null;
  if (reminder.offset === "PT0M") return getMessage(locale, "schedule.reminderOnTime");
  const value = reminder.offset
    .replace(/^PT|^P/, "")
    .replace("H", ` ${getMessage(locale, "common.hoursUnit")}`)
    .replace("M", ` ${getMessage(locale, "common.minutesUnit")}`)
    .replace("D", ` ${getMessage(locale, "common.daysUnit")}`);
  return getMessage(locale, "schedule.reminderBefore", { value });
}

export function scheduleItemTitle(item: ScheduleDisplayItem) {
  return item.value.title;
}

function formatScheduleDateTime(value: string, timezone: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale, {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: timezone,
  }).format(new Date(value));
}

function formatDuration(startTime: string | null, endTime: string | null, locale: Locale) {
  if (!startTime) return getMessage(locale, "schedule.anytime");
  if (!endTime) return getMessage(locale, "schedule.durationUnset");
  const minutes = Math.round((Date.parse(endTime) - Date.parse(startTime)) / 60000);
  if (minutes <= 0) return getMessage(locale, "schedule.durationUnset");
  if (minutes < 60) return getMessage(locale, "schedule.durationMinutes", { minutes });
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder
    ? getMessage(locale, "schedule.durationHoursMinutes", { hours, minutes: remainder })
    : getMessage(locale, "schedule.durationHours", { hours });
}

export function scheduleItemMeta(
  item: ScheduleDisplayItem,
  timezone: string,
  variant: "agenda" | "chat" | "task" | "detail",
  locale: Locale = "zh-CN",
) {
  if (item.kind === "calendar") {
    if (item.value.status === "cancelled") return getMessage(locale, "schedule.cancelledCalendar");
    if (item.value.timing_kind === "anytime") {
      if (variant === "agenda") return getMessage(locale, "schedule.anytime");
      const date = new Intl.DateTimeFormat(locale, {
        month: "numeric",
        day: "numeric",
        weekday: "short",
        timeZone: "UTC",
      }).format(new Date(`${item.value.scheduled_date}T00:00:00Z`));
      return `${date} · ${getMessage(locale, "schedule.anytime")}`;
    }
    if (variant === "agenda") {
      return formatDuration(item.value.start_time, item.value.end_time, locale);
    }
    const start = formatScheduleDateTime(item.value.start_time!, timezone, locale);
    const end = item.value.end_time ? ` - ${formatScheduleTime(item.value.end_time, timezone, locale)}` : "";
    return `${start}${end}`;
  }
  if (item.value.status === "completed") return getMessage(locale, "schedule.completedTask");
  if (item.value.status === "cancelled") return getMessage(locale, "schedule.cancelledTask");
  if (variant === "agenda") return getMessage(locale, "schedule.dueTask");
  if (variant === "task") return item.value.due_at
    ? getMessage(locale, "schedule.task")
    : getMessage(locale, "schedule.unscheduled");
  return item.value.due_at
    ? `${getMessage(locale, "schedule.task")} · ${formatScheduleDateTime(item.value.due_at, timezone, locale)}`
    : getMessage(locale, "schedule.taskList");
}

export function scheduleItemStatus(item: ScheduleDisplayItem) {
  if (item.kind === "calendar") {
    if (item.value.status === "cancelled") return "cancelled";
    if (item.value.status === "completed") return "completed";
    return "open";
  }
  return item.value.status;
}
