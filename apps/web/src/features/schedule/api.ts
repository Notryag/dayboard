import { apiFetch } from "@/lib/api/client";
import type { CalendarEntry, SchedulePage, TaskItem } from "./types";

async function getSchedulePage<T>(
  path: string,
  params: URLSearchParams,
  cursor?: string,
  signal?: AbortSignal,
): Promise<SchedulePage<T>> {
  params.set("limit", "20");
  if (cursor) params.set("cursor", cursor);
  const response = await apiFetch(`${path}?${params}`, { signal });
  return response.json() as Promise<SchedulePage<T>>;
}

export function getCalendarEntryPage(
  date: string,
  cursor?: string,
  signal?: AbortSignal,
) {
  return getSchedulePage<CalendarEntry>(
    "/api/calendar-entries",
    new URLSearchParams({ date }),
    cursor,
    signal,
  );
}

export function getUndatedTaskPage(cursor?: string, signal?: AbortSignal) {
  return getSchedulePage<TaskItem>(
    "/api/task-items",
    new URLSearchParams({ status: "open", due_kind: "undated" }),
    cursor,
    signal,
  );
}

export function getDatedTaskPage(
  date: string,
  cursor?: string,
  signal?: AbortSignal,
) {
  return getSchedulePage<TaskItem>(
    "/api/task-items",
    new URLSearchParams({ status: "open", due_kind: "dated", date }),
    cursor,
    signal,
  );
}
