"use client";

import { type FormEvent, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { userFacingApiError } from "@/lib/api/client";
import { updateCalendarEntry, updateTaskItem } from "./api";
import type { ScheduleDisplayItem } from "./types";
import styles from "./ScheduleItem.module.css";

type ScheduleItemEditFormProps = {
  item: ScheduleDisplayItem;
  onCancel: () => void;
  onSaved: () => void;
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
  if (item.kind !== "calendar" || !item.value.end_time) return 60;
  return Math.max(
    5,
    Math.round((Date.parse(item.value.end_time) - Date.parse(item.value.start_time)) / 60000),
  );
}

export function ScheduleItemEditForm({
  item,
  onCancel,
  onSaved,
  timezone,
}: ScheduleItemEditFormProps) {
  const [title, setTitle] = useState(item.value.title);
  const [dateTime, setDateTime] = useState(
    toLocalInput(item.kind === "calendar" ? item.value.start_time : item.value.due_at, timezone),
  );
  const [durationMinutes, setDurationMinutes] = useState(initialDuration(item));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle || (item.kind === "calendar" && !dateTime)) return;
    setBusy(true);
    setError(null);
    try {
      if (item.kind === "calendar") {
        await updateCalendarEntry(item.value, {
          title: trimmedTitle,
          startTime: localInputToIso(dateTime, timezone),
          durationMinutes,
        });
      } else {
        await updateTaskItem(item.value, {
          title: trimmedTitle,
          dueAt: dateTime ? localInputToIso(dateTime, timezone) : null,
        });
      }
      onSaved();
    } catch (caught) {
      setError(userFacingApiError(caught, "保存失败，请刷新后重试。"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.editForm} onSubmit={(event) => void submit(event)}>
      <label>
        <span>标题</span>
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
      <label>
        <span>{item.kind === "calendar" ? "开始时间" : "截止时间"}</span>
        <input
          disabled={busy}
          onChange={(event) => setDateTime(event.target.value)}
          required={item.kind === "calendar"}
          type="datetime-local"
          value={dateTime}
        />
      </label>
      {item.kind === "calendar" ? (
        <label>
          <span>持续分钟</span>
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
        <button disabled={busy} onClick={onCancel} type="button">取消</button>
        <button className={styles.saveButton} disabled={busy} type="submit">
          {busy ? <LoaderCircle className={styles.spinner} size={16} /> : null}
          保存
        </button>
      </div>
    </form>
  );
}
