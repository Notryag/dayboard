const dateKeyFormatters = new Map<string, Intl.DateTimeFormat>();
const timeFormatters = new Map<string, Intl.DateTimeFormat>();

export function timezoneDisplayName(timezone: string) {
  return timezone === "Asia/Shanghai" ? "北京时间" : timezone;
}

const weekdayLongFormatter = new Intl.DateTimeFormat("zh-CN", {
  weekday: "long",
  timeZone: "UTC",
});
const weekdayNarrowFormatter = new Intl.DateTimeFormat("zh-CN", {
  weekday: "narrow",
  timeZone: "UTC",
});
const monthYearFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  timeZone: "UTC",
});
const accessibleDateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
  timeZone: "UTC",
});

function formatterForDateKey(timezone: string) {
  let formatter = dateKeyFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: timezone,
    });
    dateKeyFormatters.set(timezone, formatter);
  }
  return formatter;
}

function formatterForTime(timezone: string) {
  let formatter = timeFormatters.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: timezone,
    });
    timeFormatters.set(timezone, formatter);
  }
  return formatter;
}

export function dateKeyInTimezone(value: Date, timezone: string) {
  const parts = formatterForDateKey(timezone).formatToParts(value);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function dateFromKey(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

export function shiftDateKey(value: string, amount: number) {
  const date = dateFromKey(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

export function dateRangeFrom(value: string, length = 31) {
  return Array.from({ length }, (_, index) => shiftDateKey(value, index));
}

export function formatSelectedWeekday(value: string) {
  return weekdayLongFormatter.format(dateFromKey(value));
}

export function formatRailWeekday(value: string) {
  return weekdayNarrowFormatter.format(dateFromKey(value));
}

export function formatDayNumber(value: string) {
  return String(dateFromKey(value).getUTCDate());
}

export function formatMonthYear(value: string) {
  return monthYearFormatter.format(dateFromKey(value));
}

export function formatAccessibleDate(value: string) {
  return accessibleDateFormatter.format(dateFromKey(value));
}

export function formatScheduleTime(value: string, timezone: string) {
  return formatterForTime(timezone).format(new Date(value));
}
