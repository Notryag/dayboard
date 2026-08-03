"use client";

import { type FormEvent, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import { userFacingApiError } from "@/lib/api/client";
import { updateCalendarEntry, updateTaskItem } from "./api";
import { scheduleItemTitle } from "./scheduleItemPresentation";
import type { ScheduleChange, ScheduleDisplayItem } from "./types";
import styles from "./ScheduleItem.module.css";

type ScheduleItemEditFormProps = {
  item: ScheduleDisplayItem;
  onCancel: () => void;
  onSaved: (change: ScheduleChange) => void;
  timezone: string;
};

const localDateTimeFormatter = new Map<string, Intl.DateTimeFormat>();

function formatterForLocalDateTime(timezone: string) {
  let formatter = localDateTimeFormatter.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: timezone,
    });
    localDateTimeFormatter.set(timezone, formatter);
  }
  return formatter;
}

function localParts(value: Date, timezone: string) {
  const parts = formatterForLocalDateTime(timezone).formatToParts(value);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

function toLocalInput(value: string | null, timezone: string) {
  if (!value) return "";
  const parts = localParts(new Date(value), timezone);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

function localInputToIso(value: string, timezone: string) {
  const [date, time] = value.split("T");
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const targetWallTime = Date.UTC(year, month - 1, day, hour, minute);
  let instant = targetWallTime;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = localParts(new Date(instant), timezone);
    const renderedWallTime = Date.UTC(
      Number(parts.year),
      Number(parts.month) - 1,
      Number(parts.day),
      Number(parts.hour),
      Number(parts.minute),
    );
    instant += targetWallTime - renderedWallTime;
  }
  return new Date(instant).toISOString();
}

function initialDuration(item: ScheduleDisplayItem) {
  if (item.kind !== "calendar" || !item.value.start_time || !item.value.end_time) return 60;
  return Math.max(
    5,
    Math.round((Date.parse(item.value.end_time) - Date.parse(item.value.start_time)) / 60000),
  );
}

function calendarInputFromItem(item: Extract<ScheduleDisplayItem, { kind: "calendar" }>) {
  if (item.value.timing_kind === "anytime") {
    return {
      title: item.value.title,
      timingKind: "anytime" as const,
      scheduledDate: item.value.scheduled_date ?? "",
    };
  }
  return {
    title: item.value.title,
    timingKind: "timed" as const,
    startTime: item.value.start_time ?? "",
    durationMinutes: initialDuration(item),
  };
}

export function ScheduleItemEditForm({
  item,
  onCancel,
  onSaved,
  timezone,
}: ScheduleItemEditFormProps) {
  const { locale, t } = useI18n();
  const [title, setTitle] = useState(item.value.title);
  const [timingKind, setTimingKind] = useState<"timed" | "anytime">(
    item.kind === "calendar" ? item.value.timing_kind : "timed",
  );
  const [scheduledDate, setScheduledDate] = useState(
    item.kind === "calendar" ? (item.value.scheduled_date ?? "") : "",
  );
  const [dateTime, setDateTime] = useState(
    toLocalInput(item.kind === "calendar" ? item.value.start_time : item.value.due_at, timezone),
  );
  const [durationMinutes, setDurationMinutes] = useState(initialDuration(item));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (
      !trimmedTitle ||
      (item.kind === "calendar" && timingKind === "timed" && !dateTime) ||
      (item.kind === "calendar" && timingKind === "anytime" && !scheduledDate)
    ) return;
    setBusy(true);
    setError(null);
    try {
      if (item.kind === "calendar") {
        const updated = await updateCalendarEntry(
          item.value,
          timingKind === "anytime"
            ? { title: trimmedTitle, timingKind, scheduledDate }
            : {
                title: trimmedTitle,
                timingKind,
                startTime: localInputToIso(dateTime, timezone),
                durationMinutes,
              },
        );
        onSaved({
          undo: {
            label: t("schedule.modified", { title: scheduleItemTitle(item) }),
            run: async () => {
              await updateCalendarEntry(updated, calendarInputFromItem(item));
            },
          },
        });
      } else {
        const updated = await updateTaskItem(item.value, {
          title: trimmedTitle,
          dueAt: dateTime ? localInputToIso(dateTime, timezone) : null,
        });
        onSaved({
          undo: {
            label: t("schedule.modified", { title: scheduleItemTitle(item) }),
            run: async () => {
              await updateTaskItem(updated, {
                title: item.value.title,
                dueAt: item.value.due_at,
              });
            },
          },
        });
      }
    } catch (caught) {
      setError(userFacingApiError(caught, t("schedule.saveFailed"), locale));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.editForm} onSubmit={(event) => void submit(event)}>
      <label>
        <span>{t("schedule.title")}</span>
        <input
          autoFocus
          disabled={busy}
          maxLength={240}
          onChange={(event) => setTitle(event.target.value)}
          required
          type="text"
          value={title}
        />
      </label>
      {item.kind === "calendar" ? (
        <div className={styles.timingMode} role="group" aria-label={t("schedule.timeType")}>
          <button aria-pressed={timingKind === "anytime"} disabled={busy} onClick={() => setTimingKind("anytime")} type="button">{t("schedule.anytime")}</button>
          <button aria-pressed={timingKind === "timed"} disabled={busy} onClick={() => setTimingKind("timed")} type="button">{t("schedule.timed")}</button>
        </div>
      ) : null}
      <label>
        <span>{item.kind === "calendar" ? (timingKind === "anytime" ? t("schedule.date") : t("schedule.startTime")) : t("schedule.dueTime")}</span>
        <input
          disabled={busy}
          onChange={(event) => timingKind === "anytime" ? setScheduledDate(event.target.value) : setDateTime(event.target.value)}
          required={item.kind === "calendar"}
          type={item.kind === "calendar" && timingKind === "anytime" ? "date" : "datetime-local"}
          value={item.kind === "calendar" && timingKind === "anytime" ? scheduledDate : dateTime}
        />
      </label>
      {item.kind === "calendar" && timingKind === "timed" ? (
        <label>
          <span>{t("schedule.durationMinutesLabel")}</span>
          <input
            disabled={busy}
            max={10080}
            min={5}
            onChange={(event) => setDurationMinutes(event.target.valueAsNumber)}
            required
            step={5}
            type="number"
            value={durationMinutes}
          />
        </label>
      ) : null}
      {error ? <p className={styles.formError}>{error}</p> : null}
      <div className={styles.formActions}>
        <button disabled={busy} onClick={onCancel} type="button">{t("common.cancel")}</button>
        <button className={styles.saveButton} disabled={busy} type="submit">
          {busy ? <LoaderCircle className={styles.spinner} size={16} /> : null}
          {t("common.save")}
        </button>
      </div>
    </form>
  );
}
