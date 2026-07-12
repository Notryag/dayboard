import { apiFetch } from "@/lib/api/client";
import type { CalendarEntry, SchedulePage, ScheduleView, TaskItem } from "./types";

export async function getSchedulePage(
  view: ScheduleView,
  cursor?: string,
  signal?: AbortSignal,
): Promise<SchedulePage<CalendarEntry | TaskItem>> {
  const params = new URLSearchParams({ limit: "20" });
  if (cursor) params.set("cursor", cursor);

  const path = view === "tasks" ? "/api/task-items" : "/api/calendar-entries";
  if (view === "tasks") {
    params.set("status", "open");
  } else {
    params.set("period", view);
  }

  const response = await apiFetch(`${path}?${params}`, { signal });
  return response.json() as Promise<SchedulePage<CalendarEntry | TaskItem>>;
}
