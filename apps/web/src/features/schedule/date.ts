import { getMessage, type Locale } from "@/i18n";

const dateKeyFormatters = new Map<string, Intl.DateTimeFormat>();
const timeFormatters = new Map<string, Intl.DateTimeFormat>();

export function timezoneDisplayName(timezone: string, locale: Locale = "zh-CN") {
  return timezone === "Asia/Shanghai" ? getMessage(locale, "common.chinaStandardTime") : timezone;
}

const weekdayLongFormatters = new Map<Locale, Intl.DateTimeFormat>();
const weekdayNarrowFormatters = new Map<Locale, Intl.DateTimeFormat>();
const monthYearFormatters = new Map<Locale, Intl.DateTimeFormat>();
const accessibleDateFormatters = new Map<Locale, Intl.DateTimeFormat>();

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

function formatterForTime(timezone: string, locale: Locale) {
  const key = `${locale}:${timezone}`;
  let formatter = timeFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: timezone,
    });
    timeFormatters.set(key, formatter);
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

function formatterFor<T extends Locale>(
  formatters: Map<T, Intl.DateTimeFormat>,
  locale: T,
  options: Intl.DateTimeFormatOptions,
) {
  let formatter = formatters.get(locale);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" });
    formatters.set(locale, formatter);
  }
  return formatter;
}

export function formatSelectedWeekday(value: string, locale: Locale = "zh-CN") {
  return formatterFor(weekdayLongFormatters, locale, { weekday: "long" }).format(dateFromKey(value));
}

export function formatRailWeekday(value: string, locale: Locale = "zh-CN") {
  return formatterFor(weekdayNarrowFormatters, locale, { weekday: "narrow" }).format(dateFromKey(value));
}

export function formatDayNumber(value: string) {
  return String(dateFromKey(value).getUTCDate());
}

export function formatMonthYear(value: string, locale: Locale = "zh-CN") {
  return formatterFor(monthYearFormatters, locale, { year: "numeric", month: "long" }).format(dateFromKey(value));
}

export function formatAccessibleDate(value: string, locale: Locale = "zh-CN") {
  return formatterFor(accessibleDateFormatters, locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(dateFromKey(value));
}

export function formatScheduleTime(value: string, timezone: string, locale: Locale = "zh-CN") {
  return formatterForTime(timezone, locale).format(new Date(value));
}
