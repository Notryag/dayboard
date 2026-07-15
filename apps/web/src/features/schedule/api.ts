import { apiFetch } from "@/lib/api/client";
import type {
  CalendarEntry,
  RunScheduleItemGroup,
  SchedulePage,
  TaskItem,
} from "./types";

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

export async function getScheduleItemsByRunIds(
  runIds: string[],
  signal?: AbortSignal,
): Promise<RunScheduleItemGroup[]> {
  if (!runIds.length) return [];
  const params = new URLSearchParams();
  runIds.forEach((runId) => params.append("run_id", runId));
  const response = await apiFetch(`/api/schedule-items/by-runs?${params}`, { signal });
  return response.json() as Promise<RunScheduleItemGroup[]>;
}

async function mutateScheduleItem<T>(path: string, updatedAt: string): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_updated_at: updatedAt }),
  });
  return response.json() as Promise<T>;
}

export function cancelCalendarEntry(entry: CalendarEntry): Promise<CalendarEntry> {
  return mutateScheduleItem(`/api/calendar-entries/${entry.id}/cancel`, entry.updated_at);
}

export function completeCalendarEntry(entry: CalendarEntry): Promise<CalendarEntry> {
  return mutateScheduleItem(`/api/calendar-entries/${entry.id}/complete`, entry.updated_at);
}

export function completeTaskItem(task: TaskItem): Promise<TaskItem> {
  return mutateScheduleItem(`/api/task-items/${task.id}/complete`, task.updated_at);
}

export function cancelTaskItem(task: TaskItem): Promise<TaskItem> {
  return mutateScheduleItem(`/api/task-items/${task.id}/cancel`, task.updated_at);
}

export async function updateCalendarEntry(
  entry: CalendarEntry,
  input: { title: string; startTime: string; durationMinutes: number },
): Promise<CalendarEntry> {
  const response = await apiFetch(`/api/calendar-entries/${entry.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_updated_at: entry.updated_at,
      title: input.title,
      start_time: input.startTime,
      duration_minutes: input.durationMinutes,
    }),
  });
  return response.json() as Promise<CalendarEntry>;
}

export async function updateTaskItem(
  task: TaskItem,
  input: { title: string; dueAt: string | null },
): Promise<TaskItem> {
  const response = await apiFetch(`/api/task-items/${task.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_updated_at: task.updated_at,
      title: input.title,
      due_at: input.dueAt,
    }),
  });
  return response.json() as Promise<TaskItem>;
}
