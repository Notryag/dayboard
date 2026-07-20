import {
  CalendarClock,
  Coffee,
  Dumbbell,
  GraduationCap,
  House,
  ListTodo,
  MapPin,
  Package,
  Plane,
  ShoppingBag,
  Stethoscope,
  TrainFront,
  Utensils,
  Users,
  Waves,
  type LucideIcon,
} from "lucide-react";
import { formatScheduleTime } from "./date";
import type { CalendarEntry, ScheduleDisplayItem } from "./types";

export function iconForScheduleItem(title: string, kind: ScheduleDisplayItem["kind"]): LucideIcon {
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
      return `日程 · ${formatDuration(item.value.start_time, item.value.end_time)}`;
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

export function scheduleItemStatus(item: ScheduleDisplayItem) {
  if (item.kind === "calendar") {
    if (item.value.status === "cancelled") return "cancelled";
    if (item.value.status === "completed") return "completed";
    return "open";
  }
  return item.value.status;
}
